# ai_client_v6.py
import os
import json
from typing import Dict, Any, List, Optional

import google.generativeai as genai


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _init_gemini() -> None:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment")
    genai.configure(api_key=GEMINI_API_KEY)


def classify_and_rename_gemini(
    *,
    text: str,
    original_filename: str,
    categories: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    min_confidence: float = 0.85,
    filename_style: str = "semantic-kebab",
) -> Dict[str, Any]:
    """
    Call Gemini 2.0 Flash to:
      - classify into one of the configured categories
      - produce a confidence score
      - suggest a new filename
    Returns a strict JSON dict.
    """
    _init_gemini()

    metadata = metadata or {}
    category_names = [c["name"] for c in categories]

    prompt = f"""
You are Smart Sorter V6.

You must:
1. Classify the document into ONE of these categories: {category_names}
2. Provide a confidence score between 0 and 1.
3. Map the chosen category to its configured top_level_folder and target_folder.
4. Generate a new filename using style "{filename_style}".
5. Return STRICT JSON only, no extra commentary.

Filename: {original_filename}

Metadata (may be partial):
{json.dumps(metadata, ensure_ascii=False, indent=2)}

Document text (may be truncated):
\"\"\"{text[:4000]}\"\"\"

JSON response shape:
{{
  "category": "string",
  "confidence": 0.0,
  "top_level_folder": "string",
  "target_folder": "string",
  "new_filename": "string",
  "rationale": "short explanation",
  "signals": {{
    "primary": "string",
    "secondary": "string"
  }}
}}
"""

    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content(prompt)

    # Expecting pure JSON in resp.text
    return json.loads(resp.text)
