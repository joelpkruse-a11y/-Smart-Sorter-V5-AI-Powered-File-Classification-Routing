# ============================================================
# filename_v3_engine.py — Smart Sorter V5.3
# Semantic Filename Builder (AI + OCR + Metadata)
# ============================================================

import re
from pathlib import Path
from typing import Dict, Any, Optional

from utils.logging_utils import log_diag, log_warn
from utils.file_utils import sanitize_filename


# ============================================================
# ISSUER KEYS (AI Metadata)
# ============================================================

ISSUER_KEYS = [
    "issuer",
    "institution",
    "company",
    "provider",
    "bank_name",
    "organization",
    "vendor",
    "vendor_name",
    "vendor_company",
    "billing_company",
    "billing_provider",
    "service_provider",
]


# ============================================================
# ISSUER EXTRACTION
# ============================================================

def _extract_issuer(ai_result: Dict[str, Any], ocr_text: str = "") -> Optional[str]:
    """
    Extracts issuer/vendor from:
        1) AI metadata
        2) Top-level AI fields
        3) OCR heuristics
    """
    log_diag("[FILENAME] Extracting issuer...")

    if not ai_result:
        return None

    metadata = ai_result.get("metadata") or {}

    # 1) Metadata fields
    if isinstance(metadata, dict):
        for key in ISSUER_KEYS:
            val = metadata.get(key)
            if isinstance(val, str) and val.strip():
                issuer = val.strip()
                log_diag(f"[FILENAME] Issuer from metadata[{key}]: {issuer}")
                return issuer

    # 2) Top-level fields
    for key in ISSUER_KEYS:
        val = ai_result.get(key)
        if isinstance(val, str) and val.strip():
            issuer = val.strip()
            log_diag(f"[FILENAME] Issuer from ai_result[{key}]: {issuer}")
            return issuer

    # 3) OCR heuristic
    if ocr_text:
        pattern = r"(From|Issuer|Company|Provider|Institution|Vendor|Billing)\s*:\s*(.+)"
        m = re.search(pattern, ocr_text, flags=re.IGNORECASE)
        if m:
            issuer = m.group(2).strip()
            issuer = re.split(r"[\r\n]", issuer)[0].strip()
            log_diag(f"[FILENAME] Issuer from OCR heuristic: {issuer}")
            return issuer

    log_diag("[FILENAME] No issuer detected.")
    return None


# ============================================================
# DATE EXTRACTION
# ============================================================

DATE_FIELDS = [
    "statement_date",
    "invoice_date",
    "issue_date",
    "document_date",
    "date",
]

def _extract_date(metadata: Dict[str, Any]) -> str:
    """
    Extracts and normalizes a date from metadata.
    Returns YYYY-MM-DD or raw string if normalization fails.
    """
    for key in DATE_FIELDS:
        val = metadata.get(key)
        if isinstance(val, str) and val.strip():
            raw = val.strip()

            # Try YYYY-MM-DD
            m = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", raw)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

            # Try MM/DD/YYYY
            m = re.search(r"(\d{2})[-/](\d{2})[-/](\d{4})", raw)
            if m:
                return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

            # Fallback: replace slashes
            return raw.replace("/", "-")

    return ""


# ============================================================
# DOCUMENT TYPE EXTRACTION
# ============================================================

def _extract_doc_type(ai_result: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    """
    Extracts document type from metadata or category.
    """
    doc_type = (
        metadata.get("document_type")
        or metadata.get("type")
        or ai_result.get("category")
        or ""
    )

    if isinstance(doc_type, str):
        return doc_type.strip()

    return ""


# ============================================================
# PUBLIC API — BUILD V3 FILENAME
# ============================================================

def build_v3_filename(
    ai_result: Dict[str, Any],
    original_filename: str,
    ocr_text: str = "",
) -> str:
    """
    Builds a semantic filename using:
        - Issuer
        - Date
        - Document type
        - Category
        - Original extension
    """
    try:
        base_name = Path(original_filename).stem
        ext = Path(original_filename).suffix or ".pdf"

        metadata = ai_result.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        # ----------------------------------------------------
        # Extract components
        # ----------------------------------------------------
        issuer = _extract_issuer(ai_result, ocr_text) or ""
        date = _extract_date(metadata)
        doc_type = _extract_doc_type(ai_result, metadata)

        # ----------------------------------------------------
        # Build filename parts
        # ----------------------------------------------------
        parts = []

        if issuer:
            parts.append(issuer)

        if date:
            parts.append(date)

        if doc_type:
            parts.append(doc_type)

        # If nothing extracted, fall back to original name
        if not parts:
            parts.append(base_name)

        # ----------------------------------------------------
        # Final assembly
        # ----------------------------------------------------
        filename_core = " - ".join(parts)
        filename_core = sanitize_filename(filename_core)

        final_name = f"{filename_core}{ext}"

        log_diag(f"[FILENAME] Built V3 filename: {final_name}")
        return final_name

    except Exception as e:
        log_warn(f"[FILENAME] build_v3_filename failed: {e}")
        return Path(original_filename).name