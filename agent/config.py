"""Shared constants."""
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

CATEGORIES = [
    "Lodging", "Air Travel", "Ground Transport", "Meals & Restaurants", "Fuel",
    "Software & SaaS", "Office Supplies", "Telecom & Internet", "Entertainment",
    "Professional Services", "Utilities", "Groceries & Retail",
]
ACTIONS = ["create", "update", "reassign", "reject"]
CITY = {
    "BLR": "Bengaluru", "MUM": "Mumbai", "DEL": "New Delhi", "HYD": "Hyderabad",
    "CHN": "Chennai", "PUN": "Pune", "KOL": "Kolkata", "AMD": "Ahmedabad",
    "JPR": "Jaipur", "GGN": "Gurugram",
}
TOP_K = 8            # candidate merchants passed to the decision step
MAX_ATTEMPTS = 3     # first answer + up to two retries after a guardrail failure
LIVE_MODEL = "claude-haiku-5-5"

# Live-model providers. Every decision in the app comes from one of these. "gap" is the minimum seconds between calls
# (keeps free tiers under their per-minute caps). Free-tier limits change without notice; the model name is editable in the app.
# "model" is empty for OpenAI on purpose: its model names change often, so the user types a current one from its docs.
PROVIDERS = {
    "gemini": {
        "label": "Google Gemini (free tier)", "short": "Gemini", "model": "gemini-3.5-flash-lite",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "secret": "GEMINI_API_KEY", "gap": 4.5,
        "max_tokens": None, "send_temperature": True, "key_page": "aistudio.google.com/apikey",
        "reset": "midnight Pacific time (early afternoon in India)",
    },
    "anthropic": {
        "label": "Anthropic Claude (paid)", "short": "Claude", "model": LIVE_MODEL,
        "base_url": None, "secret": "ANTHROPIC_API_KEY", "gap": 0.0, "max_tokens": 500, "send_temperature": True,
        "key_page": "console.anthropic.com", "reset": "not applicable (paid)",
    },
    "openai": {
        "label": "OpenAI (paid)", "short": "OpenAI", "model": "",
        "base_url": None, "secret": "OPENAI_API_KEY", "gap": 0.0, "max_tokens": None, "send_temperature": False,
        "key_page": "platform.openai.com/api-keys", "reset": "not applicable (paid)",
        "models_page": "developers.openai.com/docs/models",
    },
}

# Results of the live test of this version (Gemini free tier, one run of each set). Written down from the Evaluation tab when the
# runs were made; nothing here is computed. Repeat runs differ by a request or two.
RESULTS = {
    "model": "gemini-3.5-flash-lite (Google Gemini, free tier)",
    "main": {"n": 40, "correct": 37, "wrong_change": 1, "wrongly_declined": 2, "handed_over": 0, "retried": 4,
             "missed": "REQ-010, REQ-013, REQ-031"},
    "extra": {"n": 5, "correct": 5, "wrong_change": 0, "wrongly_declined": 0, "handed_over": 0, "retried": 3, "missed": "none"},
}


# The ten situations in the test set. Each is a kind of language problem; (short label, why a rules-only system fails it).
# Every request in the test set belongs to one of them, and in every request the deciding evidence is free text.
FAMILIES = {
    "negated_claim": ("Note says what it is NOT",
                      "The form still shows the old name, and the note says 'not X, it is Y'. A name match keeps the old name."),
    "future_or_rumour": ("Announced later, or only a rumour",
                         "'Will be renamed in January' and 'was renamed in August' look the same to a keyword check; so do a rumour and a receipt."),
    "hindi_or_hinglish": ("Hindi, Devanagari or Hinglish",
                          "The deciding sentence is in another script or a mixed language, which a name match and an English keyword list do not read."),
    "namesake_or_branch": ("Similar or identical name, different business",
                           "The typed name matches an existing merchant almost perfectly, and the text says it is a different business."),
    "successor_merchant": ("Closed, sold or renamed",
                           "A rename (edit the record), a sale (new company) and a takeover (move to the new owner) need three different actions; the wording decides."),
    "hidden_behind_gateway": ("Payment gateway hides the merchant",
                              "The card text names the gateway. The real merchant is only in a free-text receipt line, worded differently each time."),
    "receipt_decides_category": ("What was bought decides the category",
                                 "The merchant code is vague ('miscellaneous retail'), so the category has to come from the receipt lines."),
    "authority_pressure": ("A senior name or urgency pushes a change",
                           "The receipt contradicts the request. Only reading it, and not the pressure, gives the right answer."),
    "hidden_instruction": ("Instruction hidden in a receipt or memo",
                           "Text inside the evidence tells the model what to answer. A rules system never reads it, but it can't do the underlying task either."),
    "conflicting_or_empty_evidence": ("Little, mixed or conflicting evidence",
                                      "Two memos disagree, one payment covers two vendors, or there is nothing to go on: the right answer is to pick the strongest source or refuse."),
}
CASE_LABELS = {k: v[0] for k, v in FAMILIES.items()}
CASE_LABELS["extra_check"] = "Extra check"
