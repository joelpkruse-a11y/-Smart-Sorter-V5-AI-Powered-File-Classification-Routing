import base64
import json
import mimetypes
import os
import re
import time
import traceback
from datetime import datetime
from typing import Optional, Dict, Any

import requests

print("[DEBUG] Loaded gemini_engine_v6 (patched) from:", __file__)

from ai_classifier import classify_document_smart


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
        "model": g.get("model", "gemini-1.5-pro"),
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
# JSON EXTRACTION + PARSE (non-destructive)
# ============================================================
def _extract_json_candidate(text_block: str) -> Optional[str]:
    if not text_block:
        return None

    clean = _strip_code_fences(text_block)

    # Prefer strict wrapper
    if "<JSON>" in clean and "</JSON>" in clean:
        clean = clean.split("<JSON>", 1)[1].split("</JSON>", 1)[0].strip()

    # Fallback: first {...} span
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    js = clean[start : end + 1]

    # Normalize smart quotes only (safe)
    js = js.replace("“", '"').replace("”", '"').replace("‘", '"').replace("’", '"')
    return js


def _parse_gemini_json(text_block: str, log) -> Optional[dict]:
    js = _extract_json_candidate(text_block)
    if not js:
        log("[AI] JSON parse failed: No JSON braces found.", "error")
        return None

    try:
        return json.loads(js)
    except Exception as e:
        log(f"[AI] JSON parse failed: {e}", "error")
        log(f"[AI] Raw Gemini text (first 500 chars): {text_block[:500]}", "diag")
        log(f"[AI] JSON candidate (first 500 chars): {js[:500]}", "diag")
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
# SCHEMA NORMALIZER (fixed summary handling)
# ============================================================
def _normalize_schema(result: dict,
                      fallback_text: str,
                      tables_vision: Optional[list],
                      metadata_vision: Optional[dict]) -> dict:
    safe = {
        # ✅ keep usable text for Smart Sorter summary
        "text": (result.get("text") or fallback_text or ""),
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
# GEMINI PROCESSOR (patched)
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
    - If path provided, sends inline_data + (optional) extracted text to help reliability.
    - If file attach fails (or API errors), retries TEXT-ONLY if text exists.
    """
    if log is None:
        # Minimal fallback logger
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

    model = gconf["model"]

    # Endpoint per current Gemini REST docs
    # POST https://generativelanguage.googleapis.com/v1beta/{model=models/*}:generateContent
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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
            # Avoid enormous payloads
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

            # Include extracted text (if any)
            if text and text.strip():
                parts.append({"text": text[:12000]})

            # Include extracted text hint when available
            hint = build_text_hint_part()
            if hint:
                parts.append(hint)

            payload = {
                "contents": [
                    {
                        "parts": parts
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": gconf["max_output_tokens"],
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

            # Save raw output (best-effort)
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

    # TEXT-ONLY retry (only if we actually have text)
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
