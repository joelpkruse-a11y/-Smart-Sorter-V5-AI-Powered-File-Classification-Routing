# ============================================================
# ocr_engine.py — Gemini 2.5 Flash Image OCR (Strict + Flex)
# Smart Sorter V5.3 — AI Subsystem
# ============================================================

import os
from typing import Optional
from PIL import Image

from utils.logging_utils import log_info, log_warn, log_error, log_diag

# Gemini SDK
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

# ============================================================
# MODEL CONSTANTS
# ============================================================

GEMINI_IMAGE_MODEL = "models/gemini-2.5-flash-image"

# ============================================================
# CLIENT INITIALIZATION
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if genai and GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
    log_diag("[OCR] Gemini 2.5 Flash Image client initialized.")
else:
    client = None
    if not GEMINI_API_KEY:
        log_warn("[OCR] GEMINI_API_KEY not set; OCR will fall back to Tesseract.")
    else:
        log_warn("[OCR] google-genai not installed; OCR will fall back to Tesseract.")

# ============================================================
# INTERNAL HELPERS
# ============================================================

def _extract_text_from_response(resp) -> str:
    """
    Safely extract text from Gemini response.
    """
    if not resp:
        return ""

    # Standard path
    if hasattr(resp, "text") and resp.text:
        return resp.text.strip()

    # Candidates → content → parts
    try:
        for cand in getattr(resp, "candidates", []):
            if not cand.content:
                continue
            for part in cand.content.parts:
                if hasattr(part, "text") and part.text:
                    return part.text.strip()
    except Exception:
        pass

    # Fallback: stringify
    try:
        raw = str(resp)
        return raw.strip() if raw else ""
    except Exception:
        return ""

# ============================================================
# STRICT OCR
# ============================================================

def ocr_image_strict(img: Image.Image) -> str:
    """
    Strict OCR mode — low temperature, deterministic.
    """
    if client is None:
        log_warn("[OCR] Gemini client unavailable — strict OCR skipped.")
        return ""

    try:
        log_diag("[OCR] Strict OCR request → Gemini 2.5 Flash Image")

        resp = client.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=[
                "Extract ALL readable text from this image. Return ONLY the raw text.",
                img
            ],
            generation_config=genai_types.GenerateContentConfig(
                max_output_tokens=8192,
                temperature=0.0,
                top_p=0.9,
                top_k=40
            )
        )

        text = _extract_text_from_response(resp)
        if text.strip():
            log_info(f"[OCR] Strict OCR extracted {len(text)} chars")
        else:
            log_warn("[OCR] Strict OCR returned empty text.")

        return text

    except Exception as e:
        log_warn(f"[OCR] Strict OCR failed: {e}")
        return ""

# ============================================================
# FLEX OCR
# ============================================================

def ocr_image_flex(img: Image.Image) -> str:
    """
    Flex OCR mode — higher temperature, more tolerant of noise.
    """
    if client is None:
        log_warn("[OCR] Gemini client unavailable — flex OCR skipped.")
        return ""

    try:
        log_diag("[OCR] Flex OCR request → Gemini 2.5 Flash Image")

        resp = client.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=[
                "Extract all readable text from this image. Be flexible with noise, blur, or distortions.",
                img
            ],
            generation_config=genai_types.GenerateContentConfig(
                max_output_tokens=8192,
                temperature=0.4,
                top_p=0.9,
                top_k=40
            )
        )

        text = _extract_text_from_response(resp)
        if text.strip():
            log_info(f"[OCR] Flex OCR extracted {len(text)} chars")
        else:
            log_warn("[OCR] Flex OCR returned empty text.")

        return text

    except Exception as e:
        log_warn(f"[OCR] Flex OCR failed: {e}")
        return ""

# ============================================================
# PUBLIC API — UNIFIED OCR
# ============================================================

def ocr_image(img: Image.Image) -> str:
    """
    Unified OCR pipeline:
        1) Strict OCR (Gemini 2.5 Flash Image)
        2) Flex OCR (Gemini 2.5 Flash Image)
        3) Tesseract fallback (handled in utils/ocr_utils.py)
    """
    # 1) Strict
    text = ocr_image_strict(img)
    if text.strip():
        return text

    # 2) Flex
    text = ocr_image_flex(img)
    if text.strip():
        return text

    # 3) Return empty — Tesseract fallback will handle it
    log_warn("[OCR] Gemini OCR returned no text — Tesseract fallback required.")
    return ""