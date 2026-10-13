"""Rules-only baseline (no AI). A fair reference, written before the AI test cases were scored.

What a careful engineer would build without a language model, using only structured fields and string matching:

  1. No merchant name typed                              -> reject
  2. Closest merchant name (fuzzy score >= 90):
       - established merchant and the customer edits it   -> reject (protected lock, same as the agent)
       - the transaction already points to it             -> update the typed fields
                                                             (nothing changed -> reject; a category that
                                                              disagrees with a specific MCC -> reject)
       - another merchant                                 -> reassign (reject if a specific MCC disagrees
                                                             with that merchant's category)
  3. No close name: if the typed name appears in the card text, receipts or memos -> create,
     with the category from the MCC (or the typed category when the MCC is vague); otherwise reject.

It never interprets sentences. It cannot tell "not Pillai Dhaba" from "Pillai Dhaba", "will be renamed"
from "was renamed", or Hindi from noise, and it takes the category from a code table, not from what was bought.
"""
from rapidfuzz import fuzz

NAME_MATCH = 90        # fuzzy score at which a typed name counts as an existing merchant
EVIDENCE_MATCH = 80    # fuzzy score at which a typed name counts as "seen" in the card text / receipts / memos
MCC_CAT = {            # specific codes only; 5999 (miscellaneous retail) and unknown codes give no category
    "5812": "Meals & Restaurants", "7011": "Lodging", "5411": "Groceries & Retail", "5541": "Fuel",
    "5734": "Software & SaaS", "4121": "Ground Transport", "4511": "Air Travel", "4814": "Telecom & Internet",
    "4900": "Utilities", "5943": "Office Supplies", "7832": "Entertainment", "8999": "Professional Services",
}


def _reject(reason, message):
    return {"action": "reject", "target_merchant_id": None, "fields": {}, "reason": reason, "user_message": message}


def decide(item: dict, candidates: list) -> dict:
    req, txn = item["request"], item["txn"]
    typed = str(req["proposed_name"]).strip()
    mcc_cat = MCC_CAT.get(str(txn["mcc"]))
    if not typed:
        return _reject("No merchant name was typed.", "Please tell us the merchant name.")

    best, best_s = None, 0
    for c in candidates:
        s = fuzz.WRatio(typed, c["name"])
        if s > best_s:
            best, best_s = c, s
    fields = {k: v for k, v in (("name", typed), ("website", req["proposed_website"]),
                                ("category", req["proposed_category"])) if v}

    if best and best_s >= NAME_MATCH:
        same = best["id"] == txn["currently_mapped_merchant_id"]
        changes = bool((req["proposed_website"] and req["proposed_website"] != best["website"])
                       or req["proposed_category"] != best["category"] or typed.lower() != best["name"].lower())
        if same:
            if best["established"] and changes:
                return _reject("Protected merchant.", "This merchant record cannot be edited.")
            if not changes:
                return _reject("Nothing to change.", "The merchant already matches what you typed.")
            if req["proposed_category"] != best["category"] and mcc_cat and req["proposed_category"] != mcc_cat:
                return _reject("Typed category disagrees with the MCC.", "The category does not match the card's merchant code.")
            return {"action": "update", "target_merchant_id": best["id"], "fields": fields, "reason": "same merchant",
                    "user_message": "Merchant updated."}
        if mcc_cat and best["category"] != mcc_cat:
            return _reject("MCC disagrees with the merchant's category.", "The merchant does not match the card's merchant code.")
        return {"action": "reassign", "target_merchant_id": best["id"], "fields": {}, "reason": "closest name",
                "user_message": "Transaction moved."}

    seen = " | ".join([txn["card_acceptor_name"]] + list(txn["receipt_lines"]) + list(item["related_memos"])).lower()
    if fuzz.partial_ratio(typed.lower(), seen) < EVIDENCE_MATCH:
        return _reject("Typed name not found in the card text, receipts or memos.", "We could not find this merchant on the transaction.")
    fields["category"] = mcc_cat or req["proposed_category"]
    return {"action": "create", "target_merchant_id": None, "fields": fields, "reason": "no close name",
            "user_message": "New merchant added."}
