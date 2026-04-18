# ============================================================
# ai_engine.py — Smart Sorter V5.x AI Subsystem
# ============================================================

import os
import json
import re
import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils import (
    log_info,
    log_warn,
    log_error,
    log_diag,
    log,
    sanitize_filename,
)

# If you want, you can also import extract_text_for_ai here
# from utils import extract_text_for_ai

# ============================================================
# MODEL CONSTANTS
# ============================================================

GEMINI_MODEL_PRIMARY = "gemini-pro-vision"
GEMINI_MODEL_FALLBACK = "gemini-1.5-flash"

# Qwen stage is optional; this is a placeholder name
QWEN_MODEL_NAME = "qwen-2.5-72b-instruct"

# ============================================================
# GEMINI CLIENT INITIALIZATION (GLOBAL)
# ============================================================

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if genai and GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
    log_diag("[AI] Gemini client initialized.")
else:
    client = None
    if not GEMINI_API_KEY:
        log_warn("[AI] GEMINI_API_KEY not set; Gemini calls will be skipped.")
    else:
        log_warn("[AI] google-genai not available; Gemini calls will be skipped.")

# ============================================================
# SAFE JSON REPAIR / PARSING
# ============================================================

def _repair_json(text: str) -> Any:
    """
    Attempts to repair malformed JSON returned by Gemini.
    Returns parsed object or a dict with error info.
    """
    if text is None:
        return {"error": "No text to parse", "raw": None}

    # First attempt: direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Clean up common issues
    cleaned = text.replace("\r", " ").replace("\n", " ")
    cleaned = cleaned.replace(",}", "}").replace(",]", "]")

    try:
        return json.loads(cleaned)
    except Exception:
        return {"error": "Failed to parse JSON", "raw": text}


def clean_and_parse_json(raw: Any) -> Optional[Dict[str, Any]]:
    """
    Normalizes raw AI output into a dict.
    Handles strings, dicts, and uses _repair_json for malformed JSON.
    """
    if raw is None:
        return None

    # Already a dict
    if isinstance(raw, dict):
        return raw

    # String → try parse/repair
    if isinstance(raw, str):
        parsed = _repair_json(raw)
        if isinstance(parsed, dict):
            return parsed
        return None

    # Fallback: try to dump then parse
    try:
        dumped = json.dumps(raw)
        parsed = _repair_json(dumped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None

    return None

# ============================================================
# SAFE JSON DUMP FOR DEBUG (NO CIRCULAR CRASHES)
# ============================================================

def safe_json_dump(obj: Any) -> str:
    """
    Safely serializes any Python object to JSON.
    Removes circular references and non-serializable fields.
    """

    def default(o):
        return f"<<non-serializable: {type(o).__name__}>>"

    try:
        return json.dumps(obj, indent=2, default=default)
    except Exception:
        # Last resort: convert to string
        return str(obj)


def dump_ai_debug(data: Any, filename_hint: str = "debug") -> None:
    """
    Writes AI debug data to a JSON file using safe_json_dump.
    Never raises; only logs errors.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Adjust this path if you want a different debug folder
    debug_dir = Path("C:/SmartInbox")
    debug_dir.mkdir(parents=True, exist_ok=True)
    out_path = debug_dir / f"debug_ai_{sanitize_filename(filename_hint)}_{ts}.json"

    try:
        safe = safe_json_dump(data)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(safe)
        log_info(f"[AI] Debug written: {out_path}")
    except Exception as e:
        log_error(f"[AI] Failed to write AI debug file: {e}")

# ============================================================
# CORE GEMINI CALLS
# ============================================================

def _call_gemini_model(
    model_name: str,
    text: str,
    filename: str,
    max_output_tokens: int = 8192,
    debug: bool = False,
) -> Any:
    """
    Calls Gemini with a structured prompt and returns raw text or error dict.
    """
    log_diag(f"[AI] _call_gemini_model() using model={model_name}")

    if client is None:
        log_warn("[AI] Gemini client not available; skipping call.")
        return {"error": "Gemini client not available", "raw": None}

    prompt = f"""
You are Smart Sorter V5.2 AI. Analyze the following document text and return a JSON object with:
- category: high-level document category (e.g., "Invoices", "Credentials & Account Information", "Insurance", "Taxes")
- confidence: number 0–1 indicating confidence in the category
- metadata: object with fields like issuer, account_name, policy_number, invoice_number, due_date, statement_date, person_name, etc.
- tables: array of extracted tabular data if present (each table as rows/columns)
- filename: suggested semantic filename (without path)
- summary: 3–6 sentence natural language summary of the document
- reasoning: brief explanation of why you chose the category and key metadata

Document filename: {filename}

Document text:
{text}
"""

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            generation_config=genai_types.GenerateContentConfig(
                max_output_tokens=max_output_tokens,
                temperature=0.2,
                top_p=0.9,
                top_k=40,
                response_mime_type="application/json",
            ),
        )

        raw = response.text
        if debug and raw:
            log_diag(f"[AI] Raw Gemini output (first 500 chars): {raw[:500]}...")
        return raw

    except Exception as e:
        log_error(f"[AI] Gemini call failed: {e}")
        return {"error": str(e), "raw": None}


def _call_gemini_retry_prompt(text: str, filename: str) -> Any:
    """
    Secondary prompt variant to salvage structure when primary prompts fail.
    """
    log_diag("[AI] _call_gemini_retry_prompt() invoked")

    if client is None:
        log_warn("[AI] Gemini client not available for retry prompt.")
        return {"error": "Gemini client not available", "raw": None}

    prompt = f"""
You previously failed to return valid JSON for this document.
Try again, strictly returning ONLY a JSON object with the keys:
category, confidence, metadata, tables, filename, summary, reasoning.

Document filename: {filename}

Document text:
{text}
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_PRIMARY,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=4096,
                temperature=0.1,
                top_p=0.9,
                top_k=40,
                response_mime_type="application/json",
            ),
        )
        return response.text
    except Exception as e:
        log_error(f"[AI] Gemini retry prompt failed: {e}")
        return {"error": str(e), "raw": None}

# ============================================================
# QWEN FALLBACK STAGE (NON-BREAKING PLACEHOLDER)
# ============================================================

def _call_qwen_fallback(text: str, filename: str) -> Any:
    """
    Placeholder for Qwen fallback.
    Currently logs and returns None so it never breaks the pipeline.
    You can wire this to a real Qwen client later.
    """
    log_diag(f"[AI] Qwen fallback stage invoked for {filename}")
    # TODO: integrate real Qwen client here.
    return None

# ============================================================
# FULL RETRY PIPELINE (GEMINI PRO → FLASH → RETRY PROMPT → QWEN)
# ============================================================

def run_full_retry_pipeline(text: str, filename: str) -> Optional[Dict[str, Any]]:
    """
    Always runs:
    1) Gemini Pro
    2) Gemini Flash
    3) Gemini Retry Prompt B
    4) Qwen fallback (optional, non-breaking)
    5) Regex fallback (inside clean_and_parse_json)
    """
    # -----------------------------------------------------
    # 1) Gemini Pro
    # -----------------------------------------------------
    log("[AI] Retry Pipeline: Gemini Pro", "diag")
    raw1 = _call_gemini_model(GEMINI_MODEL_PRIMARY, text, filename)

    parsed1 = None
    if raw1:
        parsed1 = clean_and_parse_json(
            raw1 if isinstance(raw1, str) else json.dumps(raw1)
        )

    if parsed1:
        parsed1["source_model"] = GEMINI_MODEL_PRIMARY
        return parsed1

    # -----------------------------------------------------
    # 2) Gemini Flash
    # -----------------------------------------------------
    log("[AI] Retry Pipeline: Gemini Flash", "diag")
    raw2 = _call_gemini_model(GEMINI_MODEL_FALLBACK, text, filename)

    parsed2 = None
    if raw2:
        parsed2 = clean_and_parse_json(
            raw2 if isinstance(raw2, str) else json.dumps(raw2)
        )

    if parsed2:
        parsed2["source_model"] = "Gemini Flash"
        return parsed2

    # -----------------------------------------------------
    # 3) Retry Prompt B
    # -----------------------------------------------------
    log("[AI] Retry Pipeline: Retry Prompt B", "diag")
    raw3 = _call_gemini_retry_prompt(text, filename)

    parsed3 = None
    if raw3:
        parsed3 = clean_and_parse_json(
            raw3 if isinstance(raw3, str) else json.dumps(raw3)
        )

    if parsed3:
        parsed3["source_model"] = "Gemini Retry"
        return parsed3

    # -----------------------------------------------------
    # 4) Qwen fallback (optional)
    # -----------------------------------------------------
    log("[AI] Retry Pipeline: Qwen Fallback", "diag")
    raw4 = _call_qwen_fallback(text, filename)

    parsed4 = None
    if raw4:
        parsed4 = clean_and_parse_json(
            raw4 if isinstance(raw4, str) else json.dumps(raw4)
        )

    if parsed4:
        parsed4["source_model"] = QWEN_MODEL_NAME
        return parsed4

    # -----------------------------------------------------
    # 5) Regex fallback (already inside clean_and_parse_json)
    # -----------------------------------------------------
    log("[AI] Retry Pipeline: No valid JSON from AI.", "warn")
    return None

# ============================================================
# ISSUER EXTRACTION (PATCHED)
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

def _extract_issuer(ai_result: Dict[str, Any], ocr_text: str = "") -> Optional[str]:
    """
    Attempts to extract an issuer/vendor from AI result metadata,
    falling back to simple regex heuristics on OCR text.
    """
    log_diag("[DEBUG] ENTERED filename_v3_engine::_extract_issuer")

    if not ai_result:
        return None

    # 1) From metadata
    metadata = ai_result.get("metadata") or {}
    if isinstance(metadata, dict):
        for key in ISSUER_KEYS:
            val = metadata.get(key)
            if isinstance(val, str) and val.strip():
                issuer = val.strip()
                log_diag(f"[ROUTE] Issuer from metadata[{key}]: {issuer}")
                return issuer

    # 2) From top-level fields
    for key in ISSUER_KEYS:
        val = ai_result.get(key)
        if isinstance(val, str) and val.strip():
            issuer = val.strip()
            log_diag(f"[ROUTE] Issuer from ai_result[{key}]: {issuer}")
            return issuer

    # 3) OCR heuristic (expanded)
    if ocr_text:
        # Now includes Vendor and Billing
        pattern = r"(From|Issuer|Company|Provider|Institution|Vendor|Billing)\s*:\s*(.+)"
        m = re.search(pattern, ocr_text, flags=re.IGNORECASE)
        if m:
            issuer = m.group(2).strip()
            issuer = re.split(r"[\r\n]", issuer)[0].strip()
            log_diag(f"[ROUTE] Issuer from OCR heuristic: {issuer}")
            return issuer

    log("[ROUTE] No issuer detected", "diag")
    return None

# ============================================================
# CATEGORY AUTO-CREATION RULES
# ============================================================

def ensure_category_folder(sorted_root: Path, category_name: str) -> Path:
    """
    Ensures the category folder exists under the sorted root.
    Returns the full path to the category folder.
    """
    safe_category = sanitize_filename(category_name or "Uncategorized")
    category_path = sorted_root / safe_category
    if not category_path.exists():
        category_path.mkdir(parents=True, exist_ok=True)
        log(f"[ROUTE] Auto-created category folder: {category_path}", "info")
    return category_path

# ============================================================
# FILENAME V3 BUILDER (PATCHED)
# ============================================================

def build_v3_filename(
    ai_result: Dict[str, Any],
    original_filename: str,
    ocr_text: str = "",
) -> str:
    """
    Builds a semantic V3 filename using AI metadata + issuer + date.
    Preserves original extension.
    """
    try:
        base_name = Path(original_filename).stem
        ext = Path(original_filename).suffix or ".pdf"

        metadata = ai_result.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        # Issuer
        issuer = _extract_issuer(ai_result, ocr_text) or metadata.get("issuer") or ""

        # Date: prefer explicit metadata dates
        date_fields = [
            "statement_date",
            "invoice_date",
            "issue_date",
            "document_date",
            "date",
        ]
        doc_date = ""
        for key in date_fields:
            val = metadata.get(key)
            if isinstance(val, str) and val.strip():
                doc_date = val.strip()
                break

        # Normalize date to YYYY-MM-DD if possible
        normalized_date = ""
        if doc_date:
            # Very simple normalization: look for YYYY-MM-DD or YYYY/MM/DD
            m = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", doc_date)
            if m:
                normalized_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            else:
                # fallback: just use raw
                normalized_date = doc_date.replace("/", "-").strip()

        # Category
        category = ai_result.get("category") or metadata.get("category") or ""

        # Build parts
        parts = []

        if issuer:
            parts.append(issuer)

        if normalized_date:
            parts.append(normalized_date)

        # Add a short type label if present
        doc_type = metadata.get("document_type") or metadata.get("type") or category
        if isinstance(doc_type, str) and doc_type.strip():
            parts.append(doc_type.strip())

        # Fallback if nothing else
        if not parts:
            parts.append(base_name)

        filename_core = " - ".join(parts)
        filename_core = sanitize_filename(filename_core)

        final_name = f"{filename_core}{ext}"
        log_diag(f"[ROUTE] V3 filename built: {final_name}")
        return final_name

    except Exception as e:
        log_error(f"[ROUTE] build_v3_filename failed: {e}")
        # Fallback to original filename
        return Path(original_filename).name