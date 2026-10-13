"""Deterministic checks applied to every decision before it is accepted."""
import re
import unicodedata

from rapidfuzz import fuzz

from .config import ACTIONS, CATEGORIES, CITY

_DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$")


def _site(s):
    return re.sub(r"^(https?://)?(www\.)?|/+$", "", str(s).lower())


def _same_value(field, a, b):
    """Two field values are the same (website ignores http/www/slash, name ignores case, category must match exactly)."""
    if field == "website":
        return _site(a) == _site(b)
    if field == "name":
        return str(a).strip().lower() == str(b).strip().lower()
    return a == b


def _rule(name, passed, detail):
    return {"rule": name, "passed": bool(passed), "detail": detail}


def _words(s):
    return re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()


def _has_phrase(text, phrase):
    """The words of `phrase` appear one after the other in `text` (case and punctuation ignored)."""
    t, p = _words(text), _words(phrase)
    return bool(p) and any(t[i:i + len(p)] == p for i in range(len(t) - len(p) + 1))


def _nonlatin(text):
    return any(ord(c) > 0x024F and unicodedata.category(c).startswith("L") for c in str(text))


def _on_transaction(name, item):
    """A name is 'on the transaction' if it is in the card text or a receipt line (a note or memo does not count)."""
    lines = [item["txn"]["card_acceptor_name"]] + list(item["txn"]["receipt_lines"])
    return any(_has_phrase(ln, name) or fuzz.partial_ratio(str(name).lower(), ln.lower()) >= 92 for ln in lines)


def _evidence_text(item):
    """Everything the customer did not write alone: card text, receipt lines and memos. The customer's own note is left out."""
    return " | ".join([item["txn"]["card_acceptor_name"]] + list(item["txn"]["receipt_lines"]) + list(item["related_memos"]))


def check(decision: dict, candidates: list, item: dict = None) -> list:
    """Return one result per applicable rule. A failed rule is a violation.

    `item` is the request with its transaction. Without it the three evidence rules are skipped (used by the rules-only baseline)."""
    res = []
    action = decision.get("action")
    fields = decision.get("fields") or {}
    target = decision.get("target_merchant_id")
    by_id = {c["id"]: c for c in candidates}

    res.append(_rule("Action is one of the four allowed", action in ACTIONS,
                     f"action = {action!r}"))
    if action not in ACTIONS:
        return res

    res.append(_rule("A reason is given", bool(str(decision.get("reason", "")).strip()), "reason must not be empty"))

    if action in ("update", "reassign"):
        res.append(_rule("Target merchant is in the candidate list", target in by_id,
                         f"target = {target!r}; candidates = {', '.join(by_id) or 'none'}"))
    if action == "update":
        t = by_id.get(target)
        res.append(_rule("Established merchant records are not edited",
                         not (t and t["established"]),
                         f"{t['name']} is an established merchant" if t and t["established"] else "target is not protected"))
        changed = [k for k in ("name", "website", "category") if fields.get(k) and not (t and _same_value(k, fields[k], t.get(k)))]
        res.append(_rule("Update changes at least one value on the record", bool(changed),
                         f"changes {', '.join(changed)}" if changed else
                         "every value given is already on the record, so nothing would change. If nothing should change, decline the correction."))
    if action in ("create", "update") and fields.get("category"):
        res.append(_rule("Category is from the allowed list", fields["category"] in CATEGORIES,
                         f"category = {fields['category']!r}"))
    if action in ("create", "update") and fields.get("website"):
        res.append(_rule("Website looks like a domain", bool(_DOMAIN.match(str(fields["website"]).lower())),
                         f"website = {fields['website']!r}"))
    if action == "create":
        res.append(_rule("New merchant has a name and a category", bool(fields.get("name")) and bool(fields.get("category")),
                         f"fields = {fields}"))
        dup = [c for c in candidates if fields.get("name") and fuzz.ratio(fields["name"].lower(), c["name"].lower()) >= 95]
        res.append(_rule("Not a duplicate of a candidate merchant", not dup,
                         f"near-duplicate of {dup[0]['name']}" if dup else "no near-duplicate found"))
    if action == "create" and fields.get("website"):
        clash = [c for c in candidates if c.get("website") and _site(c["website"]) == _site(fields["website"])]
        res.append(_rule("New merchant does not reuse another merchant's website", not clash,
                         f"{fields['website']} already belongs to {clash[0]['name']}" if clash else "no candidate uses this website"))
    if item is not None:
        res += _evidence_rules(decision, candidates, item)
    if action == "reject":
        res.append(_rule("A plain-language message for the customer is given",
                         bool(str(decision.get("user_message", "")).strip()), "user_message must not be empty"))
    return res


def violations(results: list) -> list:
    return [r for r in results if not r["passed"]]


def _evidence_rules(decision, candidates, item):
    """Three rules that tie the answer to what is on the transaction, so an accepted change is never backed by the customer's say-so alone."""
    res = []
    action = decision.get("action")
    fields = decision.get("fields") or {}
    target = decision.get("target_merchant_id")
    by_id = {c["id"]: c for c in candidates}
    note_and_all = _evidence_text(item) + " | " + item["request"]["note"]

    # 1. A new or changed name must be on the card text or the receipt, not only in a note or memo.
    if action in ("create", "update") and fields.get("name"):
        name = fields["name"]
        cur = by_id.get(target)
        unchanged = action == "update" and cur and str(cur["name"]).strip().lower() == str(name).strip().lower()
        skip = unchanged or _nonlatin(note_and_all)      # evidence in another script cannot be matched letter for letter
        res.append(_rule("A new or changed name is on the card text or the receipt",
                         skip or _on_transaction(name, item),
                         f"'{name}' is not on the card text or the receipt. A name found only in a note or a memo is not enough."))

    # 2. A reassign to a merchant in another city needs the receipt or a memo to name that merchant in full.
    if action == "reassign" and target in by_id:
        c = by_id[target]
        same_city = CITY.get(c["city"], c["city"]) == item["txn"]["city"]
        named = _has_phrase(" | ".join(list(item["txn"]["receipt_lines"]) + list(item["related_memos"])), c["name"])
        res.append(_rule("The merchant moved to fits the transaction", same_city or named,
                         f"{c['name']} is in {CITY.get(c['city'], c['city'])} but the transaction is in {item['txn']['city']}, "
                         "and no receipt line or memo names it in full."))

    # 3. A website on a new or changed record must be one the customer typed or the evidence shows.
    if action in ("create", "update") and fields.get("website"):
        w = _site(fields["website"])
        cur = by_id.get(target)
        ok = (cur and _site(cur["website"]) == w) or w == _site(item["request"]["proposed_website"]) or w in note_and_all.lower()
        res.append(_rule("The website comes from the request or the evidence", bool(ok),
                         f"'{fields['website']}' is not in the request, the receipt or the memos. Leave the website empty unless it is given."))
    return res
