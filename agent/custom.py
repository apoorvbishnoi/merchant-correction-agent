"""Build a request item from the 'type your own request' form, in the same shape as data/requests.json."""
import datetime as dt

# (code, description) pairs used in the synthetic data
MCC_OPTIONS = [
    ("5812", "Eating places and restaurants"), ("7011", "Lodging - hotels, motels, resorts"),
    ("5411", "Grocery stores and supermarkets"), ("5541", "Service stations"),
    ("5734", "Computer software stores"), ("4121", "Taxicabs and ride services"),
    ("4511", "Airlines and air carriers"), ("4814", "Telecommunication services"),
    ("4900", "Utilities - electric, water, gas"), ("5943", "Stationery and office supplies"),
    ("7832", "Motion picture theatres"), ("8999", "Professional services"), ("5999", "Miscellaneous retail"),
]


def make_item(card_text, mcc, city, amount, receipt_text, mapped_id, name, website, category, note, memo_text=""):
    desc = dict(MCC_OPTIONS).get(mcc, "Unknown")
    receipts = [ln.strip() for ln in str(receipt_text).splitlines() if ln.strip()]
    memos = [ln.strip() for ln in str(memo_text).splitlines() if ln.strip()]
    return {
        "request": {
            "proposed_name": str(name).strip(), "proposed_website": str(website).strip(), "proposed_category": category,
            "note": str(note).strip(), "request_id": "CUSTOM", "submitted_by": "You",
        },
        "txn": {
            "txn_id": "T-CUSTOM", "date": dt.date.today().isoformat(), "amount_inr": int(amount),
            "card_acceptor_name": str(card_text).strip(), "mcc": mcc, "mcc_description": desc,
            "city": str(city).strip(), "receipt_lines": receipts,
            "currently_mapped_merchant_id": mapped_id or None,
        },
        "related_memos": memos,
    }
