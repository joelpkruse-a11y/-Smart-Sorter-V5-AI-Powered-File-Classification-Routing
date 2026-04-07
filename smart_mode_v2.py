import os
import json
import re

print("[DEBUG] Loaded smart_mode_v2 from:", __file__)

LEARNED_ISSUERS_PATH = "C:/SmartInbox/learned_issuers.json"
ROUTING_HISTORY_PATH = "C:/SmartInbox/routing_history.json"


# ============================================================
# LOAD / SAVE HELPERS
# ============================================================
def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ============================================================
# NORMALIZATION + SAFE MATCHING
# ============================================================
def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _sanitize_category(s: str) -> str:
    s = _norm(s)
    s = s.replace("-", " ").replace("/", " ").replace("\\", " ")
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        return "other"

    if s in _ALIAS_MAP:
        return _ALIAS_MAP[s]

    if s in _CANONICAL:
        return s

    return "other"


def _issuer_key(issuer: str) -> str:
    issuer = _norm(issuer)
    issuer = re.sub(r"\s+", " ", issuer).strip()
    return issuer


def _safe_dynamic_cat(name: str) -> str:
    name = _norm(name)
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return (name[:40] or "other")


def _contains_token(text_l: str, token: str) -> bool:
    t = (token or "").lower().strip()
    if not t:
        return False

    if any(ch.isspace() for ch in t):
        return t in text_l

    if re.search(r"[^a-z0-9]", t):
        return t in text_l

    if len(t) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text_l) is not None

    return t in text_l


# ============================================================
# CANONICAL CATEGORIES
# ============================================================
_CANONICAL = {
    "career", "resume",
    "finance", "bank_statements", "credit_card_statements", "paystubs", "investments", "loans",
    "insurance", "claims",
    "legal", "medical",
    "taxes",
    "utilities",
    "receipts", "statements",
    "personal",
    "photos", "videos",
    "review", "other"
}

# ============================================================
# ALIASES (PATCH E APPLIED)
# ============================================================
_ALIAS_MAP = {
    "resume": "resume",
    "curriculum vitae": "resume",
    "cv": "resume",
    "job fair announcement": "career",
    "job_fair_announcement": "career",
    "hiring event": "career",
    "recruiting": "career",

    "utility bill": "utilities",
    "utility_bill": "utilities",
    "electric bill": "utilities",
    "gas bill": "utilities",
    "water bill": "utilities",
    "internet bill": "utilities",
    "cable bill": "utilities",

    "tax document": "taxes",
    "tax_document": "taxes",
    "tax form": "taxes",

    # PATCH E — IRS removed from alias map
    # "irs": "taxes",
    # "irs form": "taxes",

    "1099": "taxes",
    "1099-r": "taxes",
    "1099r": "taxes",
    "w-2": "taxes",
    "w2": "taxes",
    "1040": "taxes",

    "paystub": "paystubs",
    "pay stubs": "paystubs",
    "pay stub": "paystubs",
    "earnings statement": "paystubs",

    "credit card statement": "credit_card_statements",
    "card statement": "credit_card_statements",
    "card_statement": "credit_card_statements",

    "bank statement": "bank_statements",
    "checking statement": "bank_statements",
    "savings statement": "bank_statements",

    "sleep study report": "medical",
    "sleep study": "medical",
    "hsat": "medical",
    "home sleep apnea testing": "medical",
    "home sleep apnea test": "medical",
    "sleep apnea report": "medical",

    "bill": "personal"
}


# ============================================================
# SMART MODE V2 (PATCH E APPLIED)
# ============================================================
def smart_mode_v2(result: dict, log):
    raw_category = result.get("category", "other")
    issuer = (result.get("metadata", {}) or {}).get("issuer")
    text = result.get("text", "") or ""
    confidence = float(result.get("confidence", 0.0) or 0.0)

    category = _sanitize_category(raw_category)
    text_l = text.lower()

    learned = _load_json(LEARNED_ISSUERS_PATH, {})
    history = _load_json(ROUTING_HISTORY_PATH, {})

    # High-confidence trust mode
    if confidence >= 0.85:
        log(f"[SMART] High-confidence Gemini category accepted: {raw_category}", "diag")
        return raw_category.lower()

    # Resume detection
    resume_hits = 0
    for w in ["resume", "experience", "education", "skills", "linkedin.com/in", "objective", "professional summary"]:
        if w in text_l:
            resume_hits += 1

    if resume_hits >= 2:
        category = "resume"

    # Sleep-study detection
    sleep_hits = 0
    for w in [
        "sleep apnea", "sleep study", "hsat", "watchpat",
        "ahi", "rdi", "odi", "cpap", "apnea/hypopnea", "apnea hypopnea",
        "epworth sleepiness", "oxygen desaturation index"
    ]:
        if w in text_l:
            sleep_hits += 1

    if sleep_hits >= 2:
        category = "medical"

    # Issuer learning
    if issuer:
        issuer_clean = _issuer_key(issuer)

        # PATCH E — IRS issuer ignored unless category == taxes
        if issuer_clean == "irs" and category != "taxes":
            issuer_clean = ""

        if issuer_clean and issuer_clean not in learned:
            if category != "other" and confidence >= 0.70:
                learned[issuer_clean] = category
                _save_json(LEARNED_ISSUERS_PATH, learned)
        else:
            learned_cat = learned.get(issuer_clean)
            if learned_cat and learned_cat != "other" and learned_cat != category:
                category = learned_cat

    # Pattern matching (PATCH E — IRS removed)
    patterns = {
        "taxes": [
            # PATCH E — removed "irs"
            "internal revenue", "tax year", "form 1040", "1040", "w-2", "w2",
            "1099", "1099-r", "1099r", "gross distribution", "taxable amount",
            "federal income tax withheld", "state income tax withheld",
            "payer", "recipient", "box 1", "box 2a", "box 4", "box 12"
        ],
        "utilities": [
            "utility bill", "billing period", "invoice", "amount due", "total due",
            "due date", "past due", "service address", "account number", "charges",
            "mediacom", "midamerican", "alliant", "centurylink", "metronet"
        ],
        "paystubs": [
            "pay stub", "paystub", "earnings statement", "pay period",
            "gross pay", "net pay", "ytd", "year to date", "withholding",
            "federal withholding", "social security", "medicare"
        ],
        "credit_card_statements": [
            "credit limit", "minimum payment", "payment due date", "statement closing date",
            "annual percentage rate", "apr", "account ending in", "mastercard", "visa",
            "capital one", "capitalone.com", "discover", "amex", "world mastercard"
        ],
        "bank_statements": [
            "checking account", "savings account", "routing number", "account summary",
            "deposit", "withdrawal", "ending balance", "beginning balance"
        ],
        "insurance": [
            "claim", "policy", "coverage", "premium", "deductible", "eob",
            "explanation of benefits", "reimbursement"
        ],
        "medical": [
            "patient", "diagnosis", "provider", "clinic", "hospital",
            "procedure", "copay", "prescription",
            "sleep apnea", "sleep study", "hsat", "watchpat",
            "ahi", "rdi", "odi", "cpap", "epworth sleepiness",
            "home sleep apnea testing", "oxygen desaturation index"
        ],
        "legal": [
            "court", "agreement", "contract", "attorney", "settlement", "case number"
        ],
        "receipts": [
            "receipt", "subtotal", "purchase", "amount due", "tax:", "tip"
        ],
        "statements": [
            "statement period", "ending balance", "beginning balance", "statement date"
        ],
        "career": [
            "job fair", "hiring event", "recruiting", "interview", "job opening"
        ]
    }

    def multi_hit(cat: str, needed: int = 2) -> bool:
        hits = 0
        for w in patterns.get(cat, []):
            if _contains_token(text_l, w):
                hits += 1
        if hits >= needed:
            return True
        return False

    if category != "resume":
        if multi_hit("medical", 2):
            category = "medical"
        elif multi_hit("taxes", 2):
            category = "taxes"
        elif multi_hit("utilities", 2):
            category = "utilities"
        elif multi_hit("paystubs", 2):
            category = "paystubs"
        elif multi_hit("credit_card_statements", 2):
            category = "credit_card_statements"
        elif multi_hit("bank_statements", 2):
            category = "bank_statements"

    # Safe overrides
    allow_override = (category == "other") or (confidence < 0.60)

    if category in (
        "utilities", "resume", "taxes", "paystubs",
        "credit_card_statements", "bank_statements", "medical"
    ):
        allow_override = False

    if allow_override:
        for cat, words in patterns.items():
            for w in words:
                if _contains_token(text_l, w):
                    category = cat
                    break
            if category == cat:
                break

    # Routing history boost
    if category == "other" and confidence < 0.40 and history:
        top_cat = max(history.items(), key=lambda kv: kv[1])[0]
        top_cat = _sanitize_category(top_cat)
        if top_cat != "other":
            category = top_cat

    # Dynamic category creation
    if category == "other" and confidence < 0.20 and issuer:
        new_cat = _safe_dynamic_cat(issuer)
        if new_cat and new_cat != "other" and new_cat not in _CANONICAL:
            category = new_cat

    history[category] = history.get(category, 0) + 1
    _save_json(ROUTING_HISTORY_PATH, history)

    return category
