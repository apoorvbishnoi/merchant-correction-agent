"""Candidate retrieval: two paths, as in the Ramp write-up.

Path 1 - similarity: character n-gram TF-IDF between the card text on the
         transaction and the card texts already mapped to each merchant.
Path 2 - name match: fuzzy match between the merchant name the customer typed
         and every merchant name.
Path 3 - mentions: merchants whose exact name appears in the receipt lines, memos or the
         customer's note (added so a merchant hidden behind a payment gateway can still be found;
         this path is an addition to the two in the Ramp write-up). Finding a mention does not
         say what the mention means: "not Orchid Bazaar" is a mention too.
The merchant the transaction is currently mapped to is always added.
"""
import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import CITY, DATA, TOP_K

_GATEWAY = re.compile(r"^(PG\*|POS |ECOM\*|MPOS\*)")


def clean_acceptor(text: str) -> str:
    text = _GATEWAY.sub("", str(text).upper())
    text = re.sub(r"[0-9]+", " ", text)
    text = re.sub(r"[^A-Z ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def evidence_text(item: dict) -> str:
    """Free text of a request that the mention search looks through."""
    return " ".join(list(item["txn"]["receipt_lines"]) + list(item["related_memos"]) + [item["request"]["note"]])


def load_merchants() -> pd.DataFrame:
    df = pd.read_csv(DATA / "merchants.csv", dtype=str).fillna("")
    df["established"] = df["established"].astype(int).astype(bool)
    df["acceptors"] = df["known_acceptors"].str.split("|")
    return df


class Retriever:
    def __init__(self, merchants: pd.DataFrame, k: int = TOP_K, per_path: int = 5):
        self.m = merchants.reset_index(drop=True)
        self.k, self.per_path = k, per_path
        profiles = [" ".join(clean_acceptor(a) for a in accs) for accs in self.m["acceptors"]]
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True)
        self.X = self.vec.fit_transform(profiles)
        self.names = self.m["name"].tolist()
        self.norm_names = [re.sub(r"[^a-z0-9&]+", " ", n.lower()).strip() for n in self.names]
        self.id_to_row = {mid: i for i, mid in enumerate(self.m["id"])}

    def _row(self, i, score, via):
        r = self.m.iloc[i]
        return {
            "id": r["id"], "name": r["name"], "website": r["website"], "category": r["category"],
            "established": bool(r["established"]), "score": round(float(score), 3), "via": via,
            "known_acceptors": list(r["acceptors"])[:2], "city": CITY.get(r["city"], r["city"]),
        }

    def candidates(self, acceptor: str, proposed_name: str, current_id=None, text: str = ""):
        q = clean_acceptor(acceptor)
        sim = cosine_similarity(self.vec.transform([q]), self.X).ravel() if q else np.zeros(len(self.m))
        if proposed_name and proposed_name.strip():
            name = process.cdist([proposed_name.strip()], self.names, scorer=fuzz.WRatio)[0] / 100.0
        else:
            name = np.zeros(len(self.m))
        pool = {}
        for i in np.argsort(-sim)[: self.per_path]:
            if sim[i] > 0:
                pool.setdefault(int(i), set()).add("similarity")
        for i in np.argsort(-name)[: self.per_path]:
            if name[i] >= 0.6:
                pool.setdefault(int(i), set()).add("name")
        score = {i: max(sim[i], name[i]) for i in pool}
        if text:
            padded = " " + re.sub(r"[^a-z0-9&]+", " ", text.lower()).strip() + " "
            hits = [i for i, nm in enumerate(self.norm_names) if len(nm) >= 6 and f" {nm} " in padded]
            for i in hits[: self.per_path]:
                pool.setdefault(i, set()).add("mention")
                score[i] = max(score.get(i, 0.0), 0.95)
        ranked = sorted(pool, key=lambda i: -score[i])[: self.k]
        out = [self._row(i, score[i], "+".join(sorted(pool[i]))) for i in ranked]
        if current_id and current_id in self.id_to_row and current_id not in {c["id"] for c in out}:
            i = self.id_to_row[current_id]
            out.append(self._row(i, max(sim[i], name[i]), "current mapping"))
        return out
