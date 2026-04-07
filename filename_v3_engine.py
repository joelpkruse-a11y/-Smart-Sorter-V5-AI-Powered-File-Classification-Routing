import os
import re
from datetime import datetime
from typing import Dict, Any, List

from utils import log


# -----------------------------
# Date extraction
# -----------------------------
_DATE_PATTERNS = [
    r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b",
    r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b",
    r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b",
]


def _sanitize(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"[^\w\- ]+", "", text)
    text = re.sub(r"\s+", "_", text)
    return text[:80]


def _extract_dates_from_text(text: str) -> List[datetime]:
    dates = []
    if not text:
        return dates

    for pattern in _DATE_PATTERNS:
        for m in re.finditer(pattern, text):
            try:
                if pattern == _DATE_PATTERNS[0]:
                    y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                elif pattern == _DATE_PATTERNS[1]:
                    mth, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if y < 100:
                        y += 2000
                else:
                    month_name, d, y = m.group(1), int(m.group(2)), int(m.group(3))
                    mth = datetime.strptime(month_name[:3], "%b").month
                dates.append(datetime(y, mth, d))
            except Exception:
                continue
    return dates


def _extract_date_from_metadata(metadata: Dict[str, Any]) -> str | None:
    if not metadata:
        return None

    for key in ("created", "modified", "creation_time", "modified_time"):
        val = metadata.get(key)
        if not val:
            continue
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(val))
        if m:
            y, mth, d = m.groups()
            return f"{y}-{mth}-{d}"

    return None


def _choose_primary_date(text: str, metadata: Dict[str, Any]) -> str | None:
    meta_date = _extract_date_from_metadata(metadata)
    if meta_date:
        return meta_date

    dates = _extract_dates_from_text(text or "")
    if dates:
        return sorted(dates)[0].strftime("%Y-%m-%d")

    return None


# -----------------------------
# Issuer / entity / doc type
# -----------------------------
_VENDOR_KEYS = [
    "issuer", "vendor", "vendor_name", "merchant", "company", "company_name",
    "provider", "service_provider", "utility_company", "payer", "institution",
    "sender"
]

_ENTITY_KEYS = [
    "pet_name", "patient_name", "member_name", "employee_name", "person_name"
]

_DOC_TYPE_PATTERNS = [
    ("PetClaim",  [r"pet claim form", r"claim form", r"pet insurance claim"]),
    ("Invoice",   [r"invoice", r"amount due", r"bill"]),
    ("Statement", [r"statement", r"account summary", r"statement period"]),
    ("EOB",       [r"explanation of benefits", r"\beob\b"]),
    ("Policy",    [r"policy", r"declarations page", r"renewal notice"]),
    ("VisitSummary", [r"visit summary", r"discharge summary"]),
    ("TaxForm",   [r"\b1099\b", r"\b1040\b", r"\bw-2\b", r"\bw2\b"]),
    ("SleepStudyReport", [r"sleep apnea", r"sleep study", r"hsat", r"watchpat"]),
]


# -----------------------------
# PATCH A + D + E
# -----------------------------
def _extract_issuer(metadata: Dict[str, Any], text: str, category: str, original_path: str) -> str | None:
    """
    PATCH A — IRS suppressed unless category == taxes
    PATCH D — XLSX files ignore issuer entirely
    PATCH E — IRS not inferred from text for non-tax docs
    """

    # XLSX → no issuer
    if original_path.lower().endswith(".xlsx"):
        return None

    # Metadata issuer
    for k in _VENDOR_KEYS:
        v = metadata.get(k)
        if isinstance(v, str) and v.strip():
            if v.strip().lower() == "irs" and category != "taxes":
                return None
            return v.strip()

    # Text-based fallback
    t = (text or "").lower()
    if "irs" in t:
        if category == "taxes":
            return "IRS"
        return None

    return None


def _extract_primary_entity(metadata: Dict[str, Any], text: str) -> str | None:
    for k in _ENTITY_KEYS:
        v = metadata.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    m = re.search(r"pet name[:\s]+([A-Za-z]{2,20})", (text or ""), re.IGNORECASE)
    if m:
        return m.group(1)

    return None


def _infer_doc_type(text: str, gem_filename: str, reasoning: str, category: str) -> str:
    blob = " ".join([text or "", gem_filename or "", reasoning or ""]).lower()

    for label, patterns in _DOC_TYPE_PATTERNS:
        for p in patterns:
            if re.search(p, blob):
                return label

    if category:
        return category.capitalize()

    return "Document"


# -----------------------------
# Public API (patched)
# -----------------------------
def build_v3_filename(
    category: str,
    metadata: Dict[str, Any],
    text: str,
    gem_filename: str,
    reasoning: str,
    original_path: str,
) -> str:
    """
    Filename V3 – patched for Gemini high-confidence trust mode + IRS suppression.
    """

    ext = os.path.splitext(original_path)[1].lower() or ".pdf"

    # -----------------------------
    # 1. Extract primary date
    # -----------------------------
    primary_date = _choose_primary_date(text, metadata)

    # -----------------------------
    # 2. Extract issuer/entity/doc type (patched)
    # -----------------------------
    issuer = _extract_issuer(metadata, text, category, original_path)
    entity = _extract_primary_entity(metadata, text)
    doc_type = _infer_doc_type(text, gem_filename, reasoning, category)

    # -----------------------------
    # 3. Clean fragments
    # -----------------------------
    cat_clean = _sanitize(category or "Other")
    issuer_clean = _sanitize(issuer) if issuer else ""
    entity_clean = _sanitize(entity) if entity else ""
    doc_type_clean = _sanitize(doc_type)
    date_clean = _sanitize(primary_date) if primary_date else ""

    # -----------------------------
    # 4. Build filename parts
    # -----------------------------
    parts = [cat_clean]

    if issuer_clean:
        parts.append(issuer_clean)

    if doc_type_clean:
        parts.append(doc_type_clean)

    if entity_clean:
        parts.append(entity_clean)

    if date_clean:
        parts.append(date_clean)

    base = "_".join([p for p in parts if p]) or "Document"
    filename = f"{base}{ext}"

    log(f"[V3] Synthesized semantic filename: {filename}", "diag")
    return filename
