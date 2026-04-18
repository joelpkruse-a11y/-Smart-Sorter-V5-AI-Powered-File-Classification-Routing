# ============================================================
# ai_engine.py — Smart Sorter V5.3
# Gemini 2.5 Flash (Text) + Gemini 2.5 Flash Image (OCR)
# ============================================================

import json
from pathlib import Path

from google import genai
from google.genai import types

from utils.logging_utils import (
    log_info,
    log_warn,
    log_error,
    log_diag,
)
from utils.file_utils import safe_open


# ============================================================
# GEMINI CLIENTS (FIXED — no model= in constructor)
# ============================================================

try:
    TEXT_CLIENT = genai.Client()
    log_diag("[AI] Gemini Flash client initialized.")
except Exception as e:
    TEXT_CLIENT = None
    log_error(f"[AI] Failed to initialize Gemini Flash: {e}")

try:
    OCR_CLIENT = genai.Client()
    log_diag("[OCR] Gemini Flash Image client initialized.")
except Exception as e:
    OCR_CLIENT = None
    log_error(f"[OCR] Failed to initialize Gemini Flash Image: {e}")


# ============================================================
# OCR USING GEMINI FLASH IMAGE
# ============================================================

def ocr_with_gemini(path: Path) -> str:
    """
    Strict OCR using Gemini 2.5 Flash Image.
    """
    if not OCR_CLIENT:
        log_warn("[OCR] OCR client unavailable.")
        return ""

    try:
        with safe_open(path, "rb") as f:
            img_bytes = f.read()

        result = OCR_CLIENT.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                "Extract ALL text. No summaries. No interpretation. Strict OCR only."
            ],
        )

        text = result.text or ""
        return text.strip()

    except Exception as e:
        log_warn(f"[OCR] OCR failed for {path.name}: {e}")
        return ""


# ============================================================
# MAIN ANALYSIS FUNCTION
# ============================================================

def analyze_with_gemini(path: Path, ocr_text: str) -> dict:
    """
    Unified document analysis using Gemini 2.5 Flash.
    Returns structured JSON.
    """
    if not TEXT_CLIENT:
        log_error("[AI] Gemini Flash client unavailable.")
        return {}

    prompt = f"""
You are a document intelligence engine. Analyze the document using the OCR text below.

OCR TEXT:
{ocr_text}

Return ONLY valid JSON with:
- category: string
- metadata: object
- summary: string (3–6 sentences)
"""

    try:
        result = TEXT_CLIENT.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        parsed = json.loads(result.text)
        return parsed

    except Exception as e:
        log_error(f"[AI] analyze_with_gemini failed: {e}")
        return {}


# ============================================================
# SUPPORTING FUNCTIONS
# ============================================================

def classify_text(text: str) -> str:
    """
    Lightweight classifier using Gemini Flash.
    """
    if not TEXT_CLIENT:
        return "other"

    prompt = f"""
Classify the following text into a single category:
{text}

Return ONLY the category name.
"""

    try:
        result = TEXT_CLIENT.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
            ),
        )
        return result.text.strip().lower()

    except Exception:
        return "other"


def extract_metadata(text: str) -> dict:
    """
    Extract structured metadata.
    """
    if not TEXT_CLIENT:
        return {}

    prompt = f"""
Extract metadata from the following text. Return ONLY JSON.

TEXT:
{text}
"""

    try:
        result = TEXT_CLIENT.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        return json.loads(result.text)

    except Exception:
        return {}


def summarize_text(text: str) -> str:
    """
    Summarize into 3–6 sentences.
    """
    if not TEXT_CLIENT:
        return ""

    prompt = f"""
Summarize the following text in 3–6 sentences:

{text}
"""

    try:
        result = TEXT_CLIENT.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )
        return result.text.strip()

    except Exception:
        return ""


# ============================================================
# RETRY PIPELINE
# ============================================================

def run_full_retry_pipeline(func, path: Path, ocr_text: str) -> dict:
    """
    Retry wrapper for analyze_with_gemini.
    """
    attempts = 3

    for i in range(1, attempts + 1):
        try:
            log_info(f"[AI] Attempt {i}/{attempts} for {path.name}")
            result = func(path, ocr_text)

            if result:
                return result

        except Exception as e:
            log_warn(f"[AI] Attempt {i} failed: {e}")

    log_error(f"[AI] All attempts failed for {path.name}")
    return {}