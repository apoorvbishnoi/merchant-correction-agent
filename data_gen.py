"""Builds the fictional merchant master list (data/merchants.csv, 242 merchants, 10 of them established).

Everything produced here is fictional. The functions below also build a first batch of rule-solvable requests;
they are kept only because the merchant list is generated together with them, so the list stays reproducible.
Those requests are NOT written out any more: the test requests live in data_gen_ai.py (see the README for why).
"""
import csv
import json
import random
import re
from pathlib import Path

SEED = 7
rng = random.Random(SEED)
OUT = Path(__file__).parent / "data"

CATEGORIES = [
    "Lodging", "Air Travel", "Ground Transport", "Meals & Restaurants", "Fuel",
    "Software & SaaS", "Office Supplies", "Telecom & Internet", "Entertainment",
    "Professional Services", "Utilities", "Groceries & Retail",
]

MCC = {
    "Lodging": ("7011", "Lodging - hotels, motels, resorts"),
    "Air Travel": ("4511", "Airlines and air carriers"),
    "Ground Transport": ("4121", "Taxicabs and ride services"),
    "Meals & Restaurants": ("5812", "Eating places and restaurants"),
    "Fuel": ("5541", "Service stations"),
    "Software & SaaS": ("5734", "Computer software stores"),
    "Office Supplies": ("5943", "Stationery and office supplies"),
    "Telecom & Internet": ("4814", "Telecommunication services"),
    "Entertainment": ("7832", "Motion picture theatres"),
    "Professional Services": ("8999", "Professional services"),
    "Utilities": ("4900", "Utilities - electric, water, gas"),
    "Groceries & Retail": ("5411", "Grocery stores and supermarkets"),
}
MCC_VAGUE = ("5999", "Miscellaneous retail")

RECEIPTS = {
    "Lodging": ["Room charges (1 night)", "Breakfast buffet", "Service charge", "Laundry"],
    "Air Travel": ["Base fare", "Airport development fee", "Web check-in", "Baggage 15 kg"],
    "Ground Transport": ["Trip fare 14.2 km", "Toll charges", "Waiting charges"],
    "Meals & Restaurants": ["Paneer butter masala", "Butter naan x4", "Jeera rice", "Soft drinks x4", "Gulab jamun"],
    "Fuel": ["Petrol 24.6 L", "Packaged water 1 L", "Snacks", "Engine oil top-up"],
    "Software & SaaS": ["Team plan, 5 seats, monthly", "Add-on storage 200 GB"],
    "Office Supplies": ["A4 paper 5 reams", "Ballpoint pens x20", "Stapler pins", "File folders x10"],
    "Telecom & Internet": ["Broadband 300 Mbps, monthly", "Static IP charge"],
    "Entertainment": ["Movie tickets x4", "Popcorn combo", "Convenience fee"],
    "Professional Services": ["Advisory retainer, September", "Filing charges", "GST on services"],
    "Utilities": ["Electricity bill, Sept", "Meter rent", "Surcharge"],
    "Groceries & Retail": ["Rice 5 kg", "Cooking oil 1 L", "Milk x6", "Detergent", "Biscuits x8"],
}

CITY = {
    "BLR": "Bengaluru", "MUM": "Mumbai", "DEL": "New Delhi", "HYD": "Hyderabad",
    "CHN": "Chennai", "PUN": "Pune", "KOL": "Kolkata", "AMD": "Ahmedabad",
    "JPR": "Jaipur", "GGN": "Gurugram",
}

NAME_TEMPLATES = {
    "Lodging": ["{w} Grand Hotel", "{w} Residency", "Hotel {w} Inn"],
    "Air Travel": ["{w} Airways", "{w} Air"],
    "Ground Transport": ["{w} Cabs", "{w} Travels", "{w} Rides"],
    "Meals & Restaurants": ["{w} Kitchen", "{w} Restaurant", "{w} Dhaba", "{w} Sweets"],
    "Fuel": ["{w} Service Station", "{w} Petro", "{w} Fuel Point"],
    "Software & SaaS": ["{w}Cloud", "{w}Soft", "{w} Labs", "{w}HQ"],
    "Office Supplies": ["{w} Stationers", "{w} Office Mart"],
    "Telecom & Internet": ["{w} Broadband", "{w} Telecom"],
    "Entertainment": ["{w} Cinemas", "{w} Arcade", "{w} Multiplex"],
    "Professional Services": ["{w} & Associates", "{w} Advisory", "{w} Legal"],
    "Utilities": ["{w} Power", "{w} Water Works"],
    "Groceries & Retail": ["{w} Mart", "{w} Supermarket", "{w} Bazaar"],
}

PLACE_WORDS = [
    "Lotus", "Orchid", "Saffron", "Kaveri", "Jasmine", "Aravali", "Deccan", "Malabar",
    "Coral", "Banyan", "Peacock", "Monsoon", "Sandal", "Tulsi", "Neem", "Chinar",
    "Gulmohar", "Amaltas", "Kesar", "Mogra", "Himal", "Nilgiri", "Konkan", "Vindhya",
    "Sahyadri", "Godavari", "Narmada", "Yamuna", "Cauvery", "Sundar", "Thar", "Malwa",
    "Awadh", "Mewar", "Kalinga", "Chola", "Hoysala", "Coorg", "Araku", "Pushkar",
    "Spiti", "Orchha", "Mandara", "Vasant", "Tarang", "Kiran", "Ananta", "Meghna",
    "Rudra", "Shikhar", "Dhara", "Pavan", "Nakshatra", "Surya", "Chandra", "Ambar",
]
TECH_WORDS = ["Nimbus", "Loom", "Forge", "Byte", "Stack", "Pulse", "Orbit", "Quill",
              "Vector", "Prism", "Lumen", "Axis", "Kite", "Beacon", "Relay", "Vertex"]
SURNAMES = ["Gill", "Mehta", "Rao", "Iyer", "Nair", "Sethi", "Bose", "Kulkarni", "Joshi",
            "Reddy", "Menon", "Chopra", "Banerjee", "Pillai", "Desai", "Naidu", "Verma",
            "Kapoor", "Bhatt", "Shetty"]
PEOPLE = ["Aarav Sharma", "Diya Nair", "Kabir Mehta", "Isha Reddy", "Rohan Iyer", "Meera Joshi",
          "Vihaan Gupta", "Anaya Bose", "Arjun Kulkarni", "Kiara Sethi", "Dev Malhotra",
          "Saanvi Pillai", "Reyansh Verma", "Navya Desai", "Krish Bhatt", "Tara Menon",
          "Ishaan Chopra", "Riya Banerjee", "Aditya Naidu", "Pooja Shetty"]
GATEWAY = ["PG*", "POS ", "ECOM*", "MPOS*", ""]

MERCHANTS = []
NAMES = set()


def slug(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def new_id():
    while True:
        mid = f"M{rng.randint(1000, 9999)}"
        if mid not in {m["id"] for m in MERCHANTS}:
            return mid


def mk_name(cat, word):
    return rng.choice(NAME_TEMPLATES[cat]).format(w=word)


def acceptor_variants(name, city, n=3):
    base = re.sub(r"[^A-Za-z0-9 ]", "", name).upper()
    squeezed = re.sub(r"(?<!^)[AEIOU]", "", base.replace(" ", ""))[:14]
    pool = [
        base[:22],
        f"{rng.choice(GATEWAY)}{base[:14]} {city}",
        f"{squeezed} {city}",
        f"{base[:12]} {rng.randint(1000, 9999)}",
    ]
    rng.shuffle(pool)
    return pool[:n]


def add_merchant(name, cat, established=False, website=None, n_acc=3):
    if name in NAMES:
        raise ValueError(f"duplicate merchant name {name}")
    NAMES.add(name)
    city = rng.choice(list(CITY))
    m = {
        "id": new_id(),
        "name": name,
        "website": website or f"{slug(name)}{rng.choice(['.in', '.com', '.co.in'])}",
        "category": cat,
        "established": established,
        "known_acceptors": acceptor_variants(name, city, n_acc),
        "city": city,
    }
    MERCHANTS.append(m)
    return m


def typo(s):
    r = rng.random()
    if r < 0.35 and len(s) > 5:
        i = rng.randint(1, len(s) - 3)
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if r < 0.6 and len(s) > 5:
        i = rng.randint(1, len(s) - 2)
        return s[:i] + s[i + 1:]
    if r < 0.8:
        return s.upper()
    return s


def cryptic(name):
    words = re.sub(r"[^A-Za-z0-9 ]", "", name).upper().split()
    out = [w[0] + re.sub(r"[AEIOU]", "", w[1:]) for w in words]
    return " ".join(out)[:20] + f" {rng.randint(1000, 9999)}"


def pick_receipts(cat, n=None):
    items = RECEIPTS[cat]
    n = n or rng.randint(2, min(3, len(items)))
    return rng.sample(items, n)


_txn_counter = [rng.randint(40000, 49000)]


def make_txn(acceptor, cat_for_mcc, receipts, mapped_id, city_code, vague_mcc=False, amount=None):
    _txn_counter[0] += rng.randint(3, 40)
    mcc, desc = MCC_VAGUE if vague_mcc else MCC[cat_for_mcc]
    return {
        "txn_id": f"T-{_txn_counter[0]}",
        "date": f"2026-09-{rng.randint(1, 28):02d}",
        "amount_inr": amount or rng.choice([480, 760, 1240, 1890, 2350, 3120, 5400, 8900, 12500]),
        "card_acceptor_name": acceptor,
        "mcc": mcc,
        "mcc_description": desc,
        "city": CITY[city_code],
        "receipt_lines": receipts,
        "currently_mapped_merchant_id": mapped_id,
    }


ITEMS = []  # each: dict(txn, request, memos, key)


def add_item(txn, req, memos, key):
    ITEMS.append({"txn": txn, "request": req, "memos": memos, "key": key})


def used_word():
    w = PLACE_WORDS.pop(rng.randrange(len(PLACE_WORDS)))
    return w


# ---------------------------------------------------------------- scenarios
def reassign_lookalike(wrong_cat, right_cat, thin=False):
    w = used_word()
    wrong = add_merchant(mk_name(wrong_cat, w), wrong_cat)
    right = add_merchant(mk_name(right_cat, w), right_cat)
    city = rng.choice(list(CITY))
    acceptor = f"{w.upper()[:11]} {rng.choice(['STN', 'OUTLET', 'SVC', 'PNT', '#'])} {rng.randint(1000, 9999)}"
    receipts = pick_receipts(right_cat, 1 if thin else None)
    txn = make_txn(acceptor, right_cat, receipts, wrong["id"], city, vague_mcc=thin)
    if thin:
        note = f"Wrong merchant. This was {right['name']}, not {wrong['name']}."
    else:
        note = rng.choice([
            f"It shows as {wrong['name']} but this was {right['name']}.",
            f"Flagged as {wrong_cat.lower()} but it is a {right_cat.lower()} charge ({right['name']}).",
            f"Please fix, merchant is {right['name']}.",
        ])
    req = {
        "proposed_name": typo(right["name"]),
        "proposed_website": right["website"] if rng.random() < 0.5 else "",
        "proposed_category": right_cat,
        "note": note,
    }
    add_item(txn, req, [], {"scenario": "reassign_lookalike", "action": "reassign", "target": right["id"]})


def reassign_cryptic(cat, generic=False):
    w = used_word()
    m = add_merchant(mk_name(cat, w), cat)
    city = rng.choice(list(CITY))
    acceptor = f"SERVICE FEE {rng.randint(1000, 9999)}" if generic else cryptic(m["name"])
    mapped = None
    if rng.random() < 0.5:
        mapped = rng.choice([x for x in MERCHANTS if not x["established"] and x["id"] != m["id"]])["id"]
    txn = make_txn(acceptor, cat, pick_receipts(cat), mapped, city, vague_mcc=generic)
    req = {
        "proposed_name": typo(m["name"]),
        "proposed_website": m["website"] if rng.random() < 0.6 else "",
        "proposed_category": cat,
        "note": rng.choice([
            f"Statement text is unreadable. The merchant is {m['name']}.",
            f"This is {m['name']}, the card shows a short code.",
            f"Unknown merchant on my statement, it is {m['name']}.",
        ]),
    }
    add_item(txn, req, [], {"scenario": "reassign_cryptic", "action": "reassign", "target": m["id"]})


def update_rebrand(cat, thin=False):
    w_old, w_new = used_word(), used_word()
    old_name, new_name = mk_name(cat, w_old), mk_name(cat, w_new)
    NAMES.add(new_name)  # reserve the new brand name
    m = add_merchant(old_name, cat)
    city = m["city"]
    new_site = f"{slug(new_name)}.in"
    txn = make_txn(m["known_acceptors"][0], cat, pick_receipts(cat), m["id"], city)
    if thin:
        note, memos = f"Name has changed, please update to {new_name}.", []
    else:
        note = f"{old_name} rebranded as {new_name} in 2024."
        memos = [f"Invoice header now reads {new_name} (formerly {old_name})."]
    req = {"proposed_name": new_name, "proposed_website": new_site, "proposed_category": cat, "note": note}
    add_item(txn, req, memos, {
        "scenario": "update_rebrand", "action": "update", "target": m["id"],
        "fields": {"name": new_name, "website": new_site},
    })


def update_category(true_cat, wrong_cat):
    w = used_word()
    m = add_merchant(mk_name(true_cat, w), wrong_cat)
    txn = make_txn(m["known_acceptors"][0], true_cat, pick_receipts(true_cat), m["id"], m["city"])
    req = {
        "proposed_name": m["name"],
        "proposed_website": "",
        "proposed_category": true_cat,
        "note": rng.choice([
            f"{m['name']} is listed under {wrong_cat}. It should be {true_cat}.",
            f"Wrong category on this merchant, it is {true_cat.lower()}.",
        ]),
    }
    add_item(txn, req, [], {
        "scenario": "update_category", "action": "update", "target": m["id"],
        "fields": {"category": true_cat},
    })


def create_new(cat, thin=False):
    w = rng.choice(SURNAMES)
    other = rng.choice([c for c in ["Meals & Restaurants", "Groceries & Retail", "Professional Services"] if c != cat])
    nm = mk_name(cat, w)
    dn = mk_name(other, w)
    if dn not in NAMES:
        add_merchant(dn, other)  # a similarly named business that is NOT the one in the request
    if nm in NAMES:
        nm = mk_name(cat, w + " " + rng.choice(["Bros", "Sons", "Co"]))
    NAMES.add(nm)  # reserve: the background fill must never create this business
    city = rng.choice(list(CITY))
    acceptor = f"{nm.upper()[:16]} {rng.randint(100, 999)}" if not thin else cryptic(nm)
    txn = make_txn(acceptor, cat, pick_receipts(cat), None, city)
    site = f"{slug(nm)}.in"
    req = {
        "proposed_name": nm,
        "proposed_website": "" if thin else site,
        "proposed_category": cat,
        "note": rng.choice([
            f"New local business, {nm}. Not in your list.",
            f"This merchant does not exist in the system. Please add {nm}.",
            f"Small vendor in {CITY[city]}, please create {nm}.",
        ]),
    }
    add_item(txn, req, [], {"scenario": "create_new", "action": "create", "fields": {"name": nm, "category": cat}})


def reject_protected(est, bad):
    city = est["city"]
    cat = est["category"]
    txn = make_txn(est["known_acceptors"][0], cat, pick_receipts(cat), est["id"], city)
    if bad == "website":
        req = {"proposed_name": est["name"], "proposed_website": rng.choice(
            ["free-gift-cards-now.biz", "claim-rewards.top", "cheapdeals-global.xyz"]),
            "proposed_category": cat, "note": "Website is wrong on this merchant. Please update it."}
    elif bad == "name":
        req = {"proposed_name": f"{rng.choice(SURNAMES)} Trading Co", "proposed_website": "",
               "proposed_category": cat, "note": "Rename this merchant, our vendor is different."}
    else:
        target = "Entertainment" if cat != "Entertainment" else "Professional Services"
        req = {"proposed_name": est["name"], "proposed_website": "", "proposed_category": target,
               "note": f"Put this under {target} so it passes our policy check."}
    add_item(txn, req, [], {"scenario": "reject_protected", "action": "reject"})


def fresh_merchant(cat):
    while True:
        try:
            return add_merchant(mk_name(cat, rng.choice(SURNAMES + PLACE_WORDS)), cat)
        except ValueError:
            continue


def reject_mismatch(true_cat, claimed_cat):
    w = used_word()
    m = add_merchant(mk_name(true_cat, w), true_cat)
    n = fresh_merchant(claimed_cat)
    txn = make_txn(m["known_acceptors"][0], true_cat, pick_receipts(true_cat), m["id"], m["city"])
    req = {
        "proposed_name": n["name"], "proposed_website": n["website"], "proposed_category": claimed_cat,
        "note": rng.choice([
            f"Please move this to {n['name']} ({claimed_cat}), it is for the team.",
            f"This should be {claimed_cat.lower()}, change the merchant to {n['name']}.",
        ]),
    }
    add_item(txn, req, [], {"scenario": "reject_mismatch", "action": "reject"})


def reject_ambiguous():
    city = rng.choice(list(CITY))
    txn = make_txn(f"CARD PURCHASE {rng.randint(1000, 9999)}", "Groceries & Retail", [], None, city, vague_mcc=True)
    req = {
        "proposed_name": rng.choice(["misc vendor", "see receipt", "shop", "vendor"]),
        "proposed_website": "",
        "proposed_category": rng.choice(CATEGORIES),
        "note": rng.choice(["", "Please fix.", "wrong merchant"]),
    }
    add_item(txn, req, [], {"scenario": "reject_ambiguous", "action": "reject"})


# ------------------------------------------------------------------ build
def build():
    # established, protected merchants
    est_specs = [
        ("ShopKart", "Groceries & Retail", "shopkart.in"), ("SkyLine Air", "Air Travel", "skylineair.in"),
        ("RideNow Cabs", "Ground Transport", "ridenow.in"), ("CloudNimbus", "Software & SaaS", "cloudnimbus.com"),
        ("FreshBasket", "Groceries & Retail", "freshbasket.in"), ("StarPlex Cinemas", "Entertainment", "starplex.in"),
        ("ConnectOne Telecom", "Telecom & Internet", "connectone.in"), ("DailyMart", "Groceries & Retail", "dailymart.in"),
        ("SwiftBite", "Meals & Restaurants", "swiftbite.in"), ("PowerGrid Utilities", "Utilities", "powergridutil.in"),
    ]
    est = [add_merchant(n, c, established=True, website=w, n_acc=5) for n, c, w in est_specs]

    # scenario items
    pairs = [("Lodging", "Fuel"), ("Lodging", "Entertainment"), ("Meals & Restaurants", "Lodging"),
             ("Groceries & Retail", "Meals & Restaurants"), ("Fuel", "Meals & Restaurants"),
             ("Entertainment", "Meals & Restaurants"), ("Lodging", "Meals & Restaurants"),
             ("Office Supplies", "Groceries & Retail")]
    for i, (a, b) in enumerate(pairs):
        reassign_lookalike(a, b, thin=(i in (2, 6)))
    for i, c in enumerate(["Ground Transport", "Meals & Restaurants", "Software & SaaS", "Lodging",
                           "Professional Services", "Fuel", "Telecom & Internet"]):
        reassign_cryptic(c, generic=(i in (2, 5)))
    for i, c in enumerate(["Software & SaaS", "Meals & Restaurants", "Lodging", "Professional Services", "Groceries & Retail"]):
        update_rebrand(c, thin=(i == 3))
    for t, w in [("Lodging", "Entertainment"), ("Meals & Restaurants", "Groceries & Retail"),
                 ("Fuel", "Ground Transport"), ("Professional Services", "Office Supplies")]:
        update_category(t, w)
    for i, c in enumerate(["Fuel", "Meals & Restaurants", "Groceries & Retail", "Office Supplies", "Lodging",
                           "Ground Transport", "Fuel", "Professional Services", "Meals & Restaurants",
                           "Utilities", "Software & SaaS", "Groceries & Retail"]):
        create_new(c, thin=(i in (3, 8, 10)))
    for e, b in zip(rng.sample(est, 4), ["website", "name", "category", "website"]):
        reject_protected(e, b)
    for t, c in [("Meals & Restaurants", "Office Supplies"), ("Lodging", "Professional Services"),
                 ("Entertainment", "Office Supplies"), ("Meals & Restaurants", "Software & SaaS")]:
        reject_mismatch(t, c)
    for _ in range(4):
        reject_ambiguous()

    # background merchants (fill the master list to ~270)
    quota = {"Lodging": 16, "Air Travel": 8, "Ground Transport": 14, "Meals & Restaurants": 34, "Fuel": 16,
             "Software & SaaS": 22, "Office Supplies": 10, "Telecom & Internet": 7, "Entertainment": 10,
             "Professional Services": 16, "Utilities": 7, "Groceries & Retail": 20}
    for cat, n in quota.items():
        made = 0
        while made < n:
            word = rng.choice(TECH_WORDS) + rng.choice(["", "ly", "io"]) if cat == "Software & SaaS" else rng.choice(
                PLACE_WORDS + SURNAMES)
            try:
                add_merchant(mk_name(cat, word), cat)
                made += 1
            except ValueError:
                continue

    rng.shuffle(ITEMS)
    requests, key = [], {}
    for i, it in enumerate(ITEMS, 1):
        rid = f"REQ-{i:03d}"
        r = dict(it["request"])
        r.update({"request_id": rid, "submitted_by": rng.choice(PEOPLE)})
        requests.append({"request": r, "txn": it["txn"], "related_memos": it["memos"]})
        key[rid] = it["key"]

    OUT.mkdir(exist_ok=True)
    rng.shuffle(MERCHANTS)
    with open(OUT / "merchants.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "website", "category", "established", "city", "known_acceptors"])
        for m in MERCHANTS:
            w.writerow([m["id"], m["name"], m["website"], m["category"], int(m["established"]), m["city"],
                        "|".join(m["known_acceptors"])])
    print(f"merchants: {len(MERCHANTS)}")


if __name__ == "__main__":
    build()
