# ============================================================
# gemini_engine.py — corrected for 2026 SDK + free-tier models
# ============================================================

import os
import json
import time
import base64
import mimetypes
from datetime import datetime
from typing import Optional, Dict, Any

import requests
from google import genai

# from local_classifier import classify_document_smart


# ============================================================
# MODEL CONSTANTS (TEXT-ONLY)
# ============================================================

GEMINI_MODEL_PRIMARY = "gemini-2.5-pro"   # text-only, free-tier eligible
GEMINI_MODEL_FALLBACK = "gemini-1.5-flash"  # text-only fallback, free-tier eligible


# ============================================================
# CONFIG LOADER
# ============================================================

def load_gemini_config(config: dict) -> dict:
    """
    Supports both:
      - config["ai_classification"]["gemini"]   (current)
      - config["gemini"]                        (legacy shortcut created by sorter)
    """
    cfg = config or {}
    g = cfg.get("gemini") or cfg.get("ai_classification", {}).get("gemini") or {}
    return {
        "enabled": bool(g.get("enabled", False)),
        "model": g.get("model", "gemini-pro-vision"),  # default for image-based flows (not used here)
        "api_key": g.get("api_key"),
        "max_output_tokens": int(g.get("max_output_tokens", 8192)),
    }


# ============================================================
# HELPERS
# ============================================================

def _normalize_windows_path(p: str) -> str:
    if not p:
        return p
    p = os.path.normpath(p).rstrip(" .")
    # Long path support
    if os.name == "nt" and len(p) >= 240 and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + os.path.abspath(p)
    return p


def encode_file_base64(path: str, retries: int = 5, delay: float = 0.7) -> str:
    """
    Reads file bytes robustly on Windows/OneDrive and returns base64 string.
    Retries handle transient locks / timing windows from sync/download processes.
    """
    path = _normalize_windows_path(path)
    last_err = None
    for _ in range(retries):
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except OSError as e:
            last_err = e
            time.sleep(delay)
    raise last_err


def detect_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _strip_code_fences(raw: str) -> str:
    if not raw:
        return raw
    raw = raw.replace("```json", "").replace("```JSON", "").replace("```", "")
    return raw.strip()


# ============================================================
# PROMPTS
# ============================================================

def build_strict_prompt() -> str:
    return """
You are a document intelligence engine. You MUST return ONLY a JSON object.

Your output MUST be wrapped EXACTLY like this:
<JSON>
{ ... }
</JSON>

No text is allowed before <JSON> or after </JSON>.
No markdown. No code fences. No commentary.

============================================================
JSON SCHEMA (YOU MUST FOLLOW THIS EXACTLY)
============================================================
{
  "text": "string",
  "category": "string",
  "confidence": 0.0,
  "metadata": {},
  "tables": [],
  "filename": "string",
  "reasoning": "string"
}

============================================================
RULES
============================================================
1) Return a JSON object that matches the schema exactly.
2) All keys MUST be enclosed in double quotes.
3) All string values MUST be enclosed in double quotes.
4) No trailing commas.
5) No additional fields beyond the schema.
6) If unknown, use empty string, 0.0, empty object {}, or empty array [].
7) DO NOT echo the schema or instructions into "text".
8) "text" should contain the extracted/recognized document text (or a concise summary if huge).

============================================================
OUTPUT FORMAT (MANDATORY)
============================================================
<JSON>
{ ...valid JSON object... }
</JSON>
""".strip()


def build_flexible_prompt() -> str:
    return """
You are a document intelligence engine.
Return ONE JSON object matching this schema (no markdown, no code fences):

{
  "text": "string",
  "category": "string",
  "confidence": 0.0,
  "metadata": {},
  "tables": [],
  "filename": "string",
  "reasoning": "string"
}

Rules:
- Return ONLY the JSON object.
- Do NOT include any explanation outside the JSON.
- Do NOT echo the schema or instructions into "text".
""".strip()


# ============================================================
# JSON EXTRACTION + REPAIR PARSER (SMART SORTER V5.3)
# Robust extraction from Gemini text output.
# Handles:
#   - <JSON> ... </JSON>
#   - Markdown code fences
#   - Multiple JSON blocks
#   - Hallucinated text around JSON
#   - Trailing commas
#   - Unescaped quotes
#   - Partial JSON recovery
# ============================================================

import json
import re

def _extract_json_candidate(text_block: str) -> Optional[str]:
    if not text_block:
        return None

    # Remove code fences
    clean = _strip_code_fences(text_block)

    # Prefer explicit <JSON> wrapper
    if "<JSON>" in clean and "</JSON>" in clean:
        try:
            clean = clean.split("<JSON>", 1)[1].split("</JSON>", 1)[0].strip()
            return clean
        except Exception:
            pass

    # Extract ALL {...} spans (Gemini sometimes returns multiple)
    spans = []
    stack = []
    start = None

    for i, ch in enumerate(clean):
        if ch == "{":
            if not stack:
                start = i
            stack.append("{")
        elif ch == "}":
            if stack:
                stack.pop()
                if not stack and start is not None:
                    spans.append(clean[start:i+1])
                    start = None

    if not spans:
        return None

    # Prefer the largest JSON block (most complete)
    candidate = max(spans, key=len)

    # Normalize smart quotes
    candidate = (
        candidate.replace("“", '"')
                 .replace("”", '"')
                 .replace("‘", '"')
                 .replace("’", '"')
    )

    return candidate.strip()


def _repair_json_string(js: str) -> str:
    """
    Minimal, safe repairs:
    - Remove trailing commas
    - Fix common quote issues
    - Remove control characters
    """
    # Remove trailing commas before } or ]
    js = re.sub(r",\s*([}\]])", r"\1", js)

    # Remove null bytes / control chars
    js = re.sub(r"[\x00-\x1F]+", " ", js)

    return js


def _parse_gemini_json(text_block: str, log) -> Optional[dict]:
    """
    Production-grade JSON parser for Gemini output.
    Steps:
      1) Extract JSON candidate
      2) Try strict json.loads
      3) Try repaired json.loads
      4) Log everything
    """

    js = _extract_json_candidate(text_block)
    if not js:
        log("[AI] JSON parse failed: No JSON candidate found.", "warn")
        return None

    # 1) Strict parse
    try:
        return json.loads(js)
    except Exception as e:
        log(f"[AI] Strict JSON parse failed: {e}", "warn")

    # 2) Repair + retry
    repaired = _repair_json_string(js)
    try:
        parsed = json.loads(repaired)
        log("[AI] JSON repaired successfully.", "diag")
        return parsed
    except Exception as e:
        log(f"[AI] Repaired JSON parse failed: {e}", "error")

    # 3) Final diagnostics
    log("[AI] JSON parse failed after repair.", "error")
    log(f"[AI] Raw Gemini text (first 500 chars): {text_block[:500]}", "diag")
    log(f"[AI] JSON candidate (first 500 chars): {js[:500]}", "diag")
    log(f"[AI] Repaired JSON (first 500 chars): {repaired[:500]}", "diag")

    return None


# ============================================================
# SAFE RESPONSE EXTRACTOR
# ============================================================

def _extract_text_block(data: dict) -> Optional[str]:
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return None
        return parts[0].get("text")
    except Exception:
        return None


# ============================================================
# FALLBACK CLASSIFIER
# ============================================================

def _fallback_local_classifier(ocr_text: str, log) -> Optional[dict]:
    """
    Best-effort fallback. classify_document_smart signature may vary;
    keep this defensive.
    """
    try:
        local = classify_document_smart(ocr_text)
        return {
            "text": ocr_text or "",
            "category": local.get("category", "other"),
            "confidence": local.get("confidence", 0.0),
            "metadata": local.get("metadata", {}) or {},
            "tables": local.get("tables", []) or [],
            "filename": local.get("filename", "document") or "document",
            "reasoning": "Gemini returned no valid JSON; fallback classifier used."
        }
    except Exception as e:
        log(f"[AI] Local classifier fallback failed: {e}", "error")
        return {
            "text": ocr_text or "",
            "category": "other",
            "confidence": 0.0,
            "metadata": {},
            "tables": [],
            "filename": "document",
            "reasoning": "Gemini failed and local fallback classifier also failed."
        }


# ============================================================
# SCHEMA NORMALIZER
# ============================================================

def _normalize_schema(result: dict,
                      fallback_text: str,
                      tables_vision: Optional[list],
                      metadata_vision: Optional[dict]) -> dict:
    safe = {
        "text": "",  # keep OCR text locally, not in Gemini JSON,
        "category": (result.get("category") or "other"),
        "confidence": float(result.get("confidence") or 0.0),
        "metadata": result.get("metadata") or {},
        "tables": result.get("tables") or [],
        "filename": (result.get("filename") or "document"),
        "reasoning": (result.get("reasoning") or ""),
    }

    if metadata_vision:
        try:
            safe["metadata"].update(metadata_vision)
        except Exception:
            pass

    if tables_vision:
        try:
            safe["tables"].extend(tables_vision)
        except Exception:
            pass

    return safe


# ============================================================
# GEMINI PROCESSOR (TEXT-ONLY, PATCHED)
# ============================================================

def gemini_process_document(
    path: str = None,
    text: str = None,
    filename: str = None,
    config: dict = None,
    log=None,
    tables_vision=None,
    metadata_vision=None,
) -> dict:
    """
    TEXT-ONLY processor:
    - Uses Gemini 2.5 Pro (text-only) via REST.
    - If Gemini fails, falls back to local classifier.
    """
    if log is None:
        def log(m, level="info"):
            print(f"[{level.upper()}] {m}")

    gconf = load_gemini_config(config or {})
    if not gconf.get("enabled"):
        log("[AI] Gemini disabled in config.json — skipping.", "diag")
        return _fallback_local_classifier(text or "", log)

    api_key = gconf.get("api_key")
    if not api_key:
        log("[AI] Gemini API key missing.", "error")
        return _fallback_local_classifier(text or "", log)

    # Force text-only model (free-tier eligible)
    model = GEMINI_MODEL_PRIMARY

    # v1 endpoint (correct)
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    def build_text_hint_part() -> Optional[dict]:
        """
        If extracted text is present, include it to prevent the model from
        classifying the prompt itself during fallback.
        """
        if text and text.strip():
            t = text.strip()
            if len(t) > 12000:
                t = t[:12000]
            return {"text": f"DOCUMENT_TEXT:\n{t}"}
        return None

    # Try strict then flexible
    for mode, prompt in [
        ("strict", build_strict_prompt()),
        ("flexible", build_flexible_prompt())
    ]:
        try:
            log(f"[AI] Gemini {mode}-mode request...", "diag")

            parts = [{"text": prompt}]

            if text and text.strip():
                parts.append({"text": text[:12000]})

            hint = build_text_hint_part()
            if hint:
                parts.append(hint)

            payload = {
                "contents": [
                    {
                        "parts": parts
                    }
                ],
                # ⭐ FIXED: v1 requires "generation_config"
                "generation_config": {
                    "max_output_tokens": gconf["max_output_tokens"],
                    "temperature": 0.0
                }
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            if resp.status_code != 200:
                log(f"[AI] Gemini API error ({resp.status_code}): {resp.text}", "error")
                continue

            data = resp.json()
            text_block = _extract_text_block(data)
            if not text_block:
                log("[AI] Gemini returned no text block.", "warn")
                continue

            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                debug_path = f"C:/SmartInbox/debug_gemini_raw_{ts}.txt"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(text_block)
                log(f"[AI] Raw Gemini output saved to {debug_path}", "diag")
            except Exception:
                pass

            result = _parse_gemini_json(text_block, log)
            if result:
                log("[AI] Gemini processing succeeded.", "success")
                return _normalize_schema(result, text or "", tables_vision, metadata_vision)

        except Exception as e:
            log(f"[AI] Gemini {mode}-mode failed: {e}", "error")

    if path and text and text.strip():
        log("[AI] Retrying Gemini in TEXT-ONLY mode...", "warn")
        return gemini_process_document(
            path=None,
            text=text,
            filename=filename,
            config=config,
            log=log,
            tables_vision=tables_vision,
            metadata_vision=metadata_vision,
        )

    log("[AI] Gemini returned no valid JSON — using fallback classifier.", "warn")
    return _fallback_local_classifier(text or "", log)

# ============================================================
# LOW-LEVEL TEXT-ONLY CALLER (SMART SORTER V5.3 — PATCHED)
# Robust Gemini text caller with strict/flex retry, logging,
# JSON-safe extraction, and full error handling.
# ============================================================

def _call_gemini_model(model_name: str, text: str, filename: str) -> Optional[str]:
    """
    Production-grade Gemini text-only call.
    - Strict → Flex retry
    - Structured logging
    - JSON-safe extraction
    - Handles empty responses
    - Handles SDK quirks
    - Used by retry pipeline
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log_warn("[GEMINI] No API key found; skipping Gemini call.")
        return None

    client = genai.Client(api_key=api_key)

    # --------------------------------------------------------
    # Build prompt
    # --------------------------------------------------------
    prompt = (
        f"{build_flexible_prompt()}\n\n"
        f"FILENAME: {filename}\n\n"
        f"DOCUMENT_TEXT:\n{text or ''}"
    )

    # --------------------------------------------------------
    # Helper: extract text safely from Gemini response
    # --------------------------------------------------------
    def _extract_text(resp):
        if not resp:
            return None

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
            return raw.strip() if raw else None
        except Exception:
            return None

    # --------------------------------------------------------
    # STRICT MODE
    # --------------------------------------------------------
    try:
        log_diag(f"[GEMINI] Strict call → {model_name}")
        resp = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=genai_types.GenerateContentConfig(
                max_output_tokens=AI_CFG.get("gemini", {}).get("max_output_tokens", 8192),
                temperature=0.2,
            ),
        )
        out = _extract_text(resp)
        if out:
            log_info(f"[GEMINI] Strict mode succeeded ({len(out)} chars).")
            return out
        log_warn("[GEMINI] Strict mode returned empty; retrying flex mode.")
    except Exception as e:
        log_warn(f"[GEMINI] Strict mode failed: {e}")

    # --------------------------------------------------------
    # FLEX MODE (retry)
    # --------------------------------------------------------
    try:
        log_diag(f"[GEMINI] Flex call → {model_name}")
        resp = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=genai_types.GenerateContentConfig(
                max_output_tokens=AI_CFG.get("gemini", {}).get("max_output_tokens", 8192),
                temperature=0.6,
            ),
        )
        out = _extract_text(resp)
        if out:
            log_info(f"[GEMINI] Flex mode succeeded ({len(out)} chars).")
            return out
        log_warn("[GEMINI] Flex mode returned empty.")
    except Exception as e:
        log_warn(f"[GEMINI] Flex mode failed: {e}")

    # --------------------------------------------------------
    # TOTAL FAILURE
    # --------------------------------------------------------
    log_warn("[GEMINI] All text-only attempts failed.")
    return None

# ============================================================
# FULL RETRY PIPELINE — SMART SORTER V5.3 (FINAL PATCH)
# Robust, logged, strict→flex, Pro→Flash, JSON-safe.
# ============================================================

def run_full_retry_pipeline(text: str, filename: str, log_fn) -> Optional[Dict[str, Any]]:
    """
    Production-grade retry pipeline for Gemini text-only models.
    Steps:
      1) Gemini 2.5 Pro (strict→flex inside _call_gemini_model)
      2) Gemini 1.5 Flash (strict→flex)
      3) JSON repair fallback (inside _parse_gemini_json)
      4) Final minimal fallback (never crashes)
    """

    # --------------------------------------------------------
    # 1) Gemini Pro
    # --------------------------------------------------------
    log_fn("[AI] Retry Pipeline: Gemini Pro", "diag")
    raw1 = _call_gemini_model(GEMINI_MODEL_PRIMARY, text, filename)

    if raw1:
        parsed1 = _parse_gemini_json(raw1, log_fn)
        if parsed1:
            parsed1["source_model"] = GEMINI_MODEL_PRIMARY
            log_fn("[AI] Retry Pipeline: Gemini Pro succeeded.", "diag")
            return parsed1
        else:
            log_fn("[AI] Retry Pipeline: Gemini Pro returned invalid JSON.", "warn")
    else:
        log_fn("[AI] Retry Pipeline: Gemini Pro returned no text.", "warn")

    # --------------------------------------------------------
    # 2) Gemini Flash (free-tier safe)
    # --------------------------------------------------------
    log_fn("[AI] Retry Pipeline: Gemini Flash", "diag")
    raw2 = _call_gemini_model(GEMINI_MODEL_FALLBACK, text, filename)

    if raw2:
        parsed2 = _parse_gemini_json(raw2, log_fn)
        if parsed2:
            parsed2["source_model"] = GEMINI_MODEL_FALLBACK
            log_fn("[AI] Retry Pipeline: Gemini Flash succeeded.", "diag")
            return parsed2
        else:
            log_fn("[AI] Retry Pipeline: Gemini Flash returned invalid JSON.", "warn")
    else:
        log_fn("[AI] Retry Pipeline: Gemini Flash returned no text.", "warn")

    # --------------------------------------------------------
    # 3) Total failure
    # --------------------------------------------------------
    log_fn("[AI] Retry Pipeline: No valid JSON from Gemini models.", "warn")
    return None