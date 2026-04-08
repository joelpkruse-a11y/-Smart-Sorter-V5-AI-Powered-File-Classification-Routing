import json
import re
from ollama import Client

# Smart Sorter will override this with its own logger if needed
def log(msg, level="info"):
    print(f"[{level.upper()}] {msg}")

# Ollama client
client = Client(host="http://localhost:11434")

# Default models (Smart Sorter may override)
AI_MODEL_FAST = "qwen2.5:0.5b"
AI_MODEL_SLOW = "qwen2.5:1.5b"

# Smart Mode thresholds
CONFIDENCE_ACCEPT = 0.90
CONFIDENCE_REFINE = 0.70

# ---------------------------------------------------------
# UNIVERSAL AI REQUEST
# ---------------------------------------------------------
def ai_request(prompt: str, model: str, temperature: float = 0.0):
    try:
        resp = client.generate(
            model=model,
            prompt=prompt,
            options={"temperature": temperature},
            stream=False
        )

        if isinstance(resp, dict):
            return (resp.get("response") or "").strip()

        if hasattr(resp, "response"):
            return str(resp.response).strip()

        return str(resp).strip()

    except Exception as e:
        log(f"AI request failed: {e}", "error")
        return ""

# ---------------------------------------------------------
# CODE-FENCE STRIPPER
# ---------------------------------------------------------
def strip_code_fences(raw: str) -> str:
    if not raw:
        return raw

    raw = raw.strip()
    raw = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE)
    raw = raw.replace("```", "")
    return raw.strip()

# ---------------------------------------------------------
# FILENAME SANITIZER
# ---------------------------------------------------------
def sanitize_filename(name: str, extension: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_ ]+", "", name)
    name = name.replace(" ", "_")
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    name = "_".join(word.capitalize() for word in name.split("_"))
    return f"{name[:80]}{extension}"

# ---------------------------------------------------------
# YEAR & DATE EXTRACTION (DETERMINISTIC)
# ---------------------------------------------------------
YEAR_REGEX = r"\b(19[0-9]{2}|20[0-9]{2}|2100)\b"

def extract_years(text: str):
    if not text:
        return []
    return re.findall(YEAR_REGEX, text)

def extract_year_from_filename(filename: str):
    return extract_years(filename)

def extract_date_from_metadata(metadata: dict) -> str | None:
    """
    Expect metadata like:
    {
      "created": "2020-08-14T12:34:56",
      "modified": "2020-08-15T09:10:11"
    }
    Returns YYYYMMDD (string) or None.
    """
    if not metadata:
        return None

    for key in ("created", "modified", "creation_time", "modified_time"):
        val = metadata.get(key)
        if not val:
            continue
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(val))
        if m:
            y, mth, d = m.groups()
            return f"{y}{mth}{d}"

    return None

# ---------------------------------------------------------
# METADATA EXTRACTION (AI)
# ---------------------------------------------------------
def extract_metadata(text: str, model: str) -> dict:
    text = text[:4000]

    prompt = f"""
You are a metadata extractor. Return ONLY valid JSON.

Extract:
- doc_type (short label)
- issuer (company, bank, provider, agency)
- year (2020–2035)
- account_number (if present)
- person_name (if present)

If unknown, use null.

Respond ONLY with:
{{
  "doc_type": "...",
  "issuer": "...",
  "year": 2024,
  "account_number": "...",
  "person_name": "..."
}}

Text:
{text}
"""

    raw = ai_request(prompt, model, temperature=0.0)
    clean = strip_code_fences(raw)

    try:
        data = json.loads(clean)
        return {
            "doc_type": data.get("doc_type"),
            "issuer": data.get("issuer"),
            "year": data.get("year"),
            "account_number": data.get("account_number"),
            "person_name": data.get("person_name"),
        }
    except Exception:
        log(f"Non‑JSON metadata response: ```json\n{raw}\n```", "error")
        return {}

# ---------------------------------------------------------
# STRICT TAX & MEDICAL KEYWORDS (OCR + FILENAME)
# ---------------------------------------------------------
TAX_KEYWORDS = [
    "w-2", "w2",
    "1099", "1099-r", "1099r", "1099-nec", "1099nec",
    "1099-misc", "1099misc", "1099-int", "1099int",
    "1099-div", "1099div", "ssa-1099",
    "1040", "1040-sr", "1040sr", "1040-x", "1040x",
    "tax return", "irs", "internal revenue service",
    "withholding", "tax statement", "tax form",
    "form w-2", "form 1099", "form 1040"
]

MEDICAL_KEYWORDS = [
    "prescription", "rx", "eye exam", "vision exam",
    "optometry", "ophthalmology", "eyeglass", "eyeglasses",
    "lens prescription", "contact lens", "medical", "clinic",
    "patient", "diagnosis", "treatment"
]

def is_tax_document(text: str, filename: str) -> bool:
    lower_text = text.lower()
    lower_file = filename.lower()
    for kw in TAX_KEYWORDS:
        if kw in lower_text or kw in lower_file:
            return True
    return False

def is_medical_document(text: str, filename: str) -> bool:
    lower_text = text.lower()
    lower_file = filename.lower()
    for kw in MEDICAL_KEYWORDS:
        if kw in lower_text or kw in lower_file:
            return True
    return False

# ---------------------------------------------------------
# SINGLE-PASS CLASSIFICATION (WITH HARD RULES + PHASE 2)
# ---------------------------------------------------------
def classify_document_single(
    text: str,
    model: str,
    temperature: float = 0.0,
    original_filename: str = "",
    ocr_confidence: float | None = None,
    metadata: dict | None = None,
    tables: list | None = None
) -> dict:
    text = text[:4000]
    metadata = metadata or {}
    tables = tables or []

    # HARD TAX RULES (OCR + filename)
    if is_tax_document(text, original_filename):
        return {
            "category": "taxes",
            "confidence": 1.0,
            "forced": True
        }

    # HARD MEDICAL RULES (OCR + filename)
    if is_medical_document(text, original_filename):
        return {
            "category": "medical",
            "confidence": 1.0,
            "forced": True
        }

    # If no text at all, don't bother the model: fall back to filename-only logic
    if not text.strip():
        return {
            "category": "other",
            "confidence": 0.0,
            "forced": False
        }

    # Base classifier prompt (text first)
    prompt = f"""
You are a document classifier. Return ONLY valid JSON.

Categories:
- finance
- insurance
- medical
- legal
- taxes
- receipts
- statements
- personal
- photos
- videos
- other

DEFINITIONS:
- "taxes" = ANY tax form (W‑2, 1099, 1040, IRS letters, state tax letters, withholding, tax summaries)
- "medical" = prescriptions, health records, bills, lab results, clinical documents
- "personal" = personal letters, notes, IDs, resumes, non‑financial personal documents
- "finance" = banking, investments, loans, credit cards
- "statements" = monthly or periodic statements (bank, credit card, utilities)
- "receipts" = proof of purchase
- "insurance" = policy documents, EOBs, claims
- "legal" = contracts, agreements, court documents

Text:
{text}
"""

    # PHASE 2: inject OCR confidence, metadata, tables
    if ocr_confidence is not None:
        prompt += f"\n\n=== OCR CONFIDENCE ===\n{ocr_confidence:.2f}\n"

    if metadata:
        prompt += "\n=== METADATA ===\n"
        for k, v in metadata.items():
            prompt += f"{k}: {v}\n"

    if tables:
        prompt += "\n=== TABLES ===\n"
        for row in tables:
            prompt += " | ".join(str(cell) for cell in row) + "\n"

    # JSON output instructions
    prompt += """
Respond ONLY with:
{
  "category": "...",
  "confidence": 0.0
}
"""

    raw = ai_request(prompt, model, temperature)
    if not raw:
        return {"category": "other", "confidence": 0.0}

    clean = strip_code_fences(raw)

    try:
        data = json.loads(clean)
        cat = (data.get("category") or "other").strip().lower()
        conf = float(data.get("confidence", 0.0))

        allowed = {
            "finance", "insurance", "medical", "legal", "taxes",
            "receipts", "statements", "personal", "photos", "videos", "other"
        }
        if cat not in allowed:
            cat = "other"

        return {"category": cat, "confidence": conf}

    except Exception:
        log(f"Non‑JSON classification response: ```json\n{raw}\n```", "error")
        return {"category": "other", "confidence": 0.0}

# ---------------------------------------------------------
# SMART MODE CLASSIFICATION (DUAL MODEL + PHASE 2)
# ---------------------------------------------------------
def classify_document_smart(
    text: str,
    original_filename: str = "",
    ocr_confidence: float | None = None,
    metadata: dict | None = None,
    tables: list | None = None
) -> dict:
    metadata = metadata or {}
    tables = tables or []

    # If no external metadata provided, fall back to AI metadata extraction
    if not metadata and text.strip():
        metadata = extract_metadata(text, AI_MODEL_FAST)

    # FAST PASS
    fast = classify_document_single(
        text,
        AI_MODEL_FAST,
        temperature=0.0,
        original_filename=original_filename,
        ocr_confidence=ocr_confidence,
        metadata=metadata,
        tables=tables
    )
    conf = fast.get("confidence", 0.0)

    # Accept immediately
    if conf >= CONFIDENCE_ACCEPT or fast.get("forced"):
        fast["source_model"] = AI_MODEL_FAST
        fast["refined"] = False
        fast["metadata"] = metadata
        return fast

    # Too low → review
    if conf < CONFIDENCE_REFINE:
        fast["source_model"] = AI_MODEL_FAST
        fast["refined"] = False
        fast["force_review"] = True
        fast["metadata"] = metadata
        return fast

    # SLOW PASS
    slow = classify_document_single(
        text,
        AI_MODEL_SLOW,
        temperature=0.0,
        original_filename=original_filename,
        ocr_confidence=ocr_confidence,
        metadata=metadata,
        tables=tables
    )
    slow["source_model"] = AI_MODEL_SLOW
    slow["refined"] = True
    slow["metadata"] = metadata
    return slow

# ---------------------------------------------------------
# DOCUMENT SUMMARY GENERATOR
# ---------------------------------------------------------
def summarize_document(text: str, metadata: dict = None, model: str = AI_MODEL_SLOW) -> dict:
    metadata = metadata or {}
    text = text[:5000]

    if not text.strip():
        return {"summary": ""}

    prompt = f"""
You are a document summarizer.

STRICT RULES:
- NEVER invent numbers, dates, or years.
- ONLY include numbers that appear in the document text.
- NEVER fabricate names, companies, or entities.
- Keep the summary factual, concise, and grounded in the text.
- 3–6 sentences maximum.
- Return ONLY valid JSON.

Metadata (may help context but DO NOT invent missing details):
{json.dumps(metadata, indent=2)}

Document text:
{text}

Respond ONLY with:
{{
  "summary": "..."
}}
"""

    raw = ai_request(prompt, model, temperature=0.2)
    clean = strip_code_fences(raw)

    try:
        data = json.loads(clean)
        summary = (data.get("summary") or "").strip()

        real_years = extract_years(text)
        if not real_years:
            summary = re.sub(r"\b20[2-3][0-9]\b", "", summary)

        digits_in_text = set(re.findall(r"\d+", text))

        def scrub_numbers(s):
            tokens = re.split(r'(\d+)', s)
            cleaned = []
            for t in tokens:
                if t.isdigit() and t not in digits_in_text:
                    continue
                cleaned.append(t)
            return "".join(cleaned)

        summary = scrub_numbers(summary)
        return {"summary": summary}

    except Exception:
        log(f"Non‑JSON summary response: ```json\n{raw}\n```", "error")
        return {"summary": ""}

# ---------------------------------------------------------
# FILENAME GENERATION (TEXT + FILENAME + METADATA)
# ---------------------------------------------------------
def generate_filename(
    text: str,
    category: str,
    original_filename: str,
    metadata: dict | None = None
) -> str:
    """
    Rules:
    - If original filename has a year → use that year.
    - Else if OCR text has a year → use that year.
    - Include date from metadata (created/modified) if available.
    - Use filename stem to keep human meaning.
    - Never invent years.
    """
    extension = "." + original_filename.split(".")[-1]
    text = (text or "")[:3000]
    metadata = metadata or {}

    stem = original_filename.rsplit(".", 1)[0]
    stem = stem.strip()

    stem = re.sub(r"\s+", " ", stem)
    stem_words = stem.split(" ")
    stem_short = " ".join(stem_words[:5])

    filename_years = extract_year_from_filename(original_filename)
    year = None
    if filename_years:
        year = min(filename_years)
    else:
        text_years = extract_years(text)
        if text_years:
            year = min(text_years)

    date_str = extract_date_from_metadata(metadata)

    parts = [category]
    if stem_short:
        parts.append(stem_short)
    if year:
        parts.append(str(year))
    if date_str:
        parts.append(date_str)

    base = "_".join(parts)
    return sanitize_filename(base, extension)