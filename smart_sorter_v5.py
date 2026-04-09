import os
import sys
import time
import json
import shutil
import traceback
from datetime import datetime
import re

import fitz
import docx
import google.generativeai as genai

def load_config():
    import json, os
    with open("config.json", "r") as f:
        config = json.load(f)
    config["ai"]["api_key"] = os.getenv("GEMINI_API_KEY")
    return config

from ai_classifier import (
    classify_document_smart,
    generate_filename,
)

from smart_mode_v2 import smart_mode_v2
from filename_router import generate_final_filename, route_file
from v3_debug_dashboard import add_event

from PIL import Image
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

print("[DEBUG] Loaded smart_sorter_v5 (Render Edition) from:", __file__)

# ---------------------------------------------------------
# Gemini 2.0 Flash scaffolding
# ---------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

def _init_gemini():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    genai.configure(api_key=GEMINI_API_KEY)

def gemini_process_document(
    *,
    path: str,
    text: str,
    filename: str,
    config: dict,
    log,
    tables_vision=None,
    metadata_vision=None,
) -> dict:
    """Strict JSON Gemini 2.0 Flash classification."""
    _init_gemini()

    tables_vision = tables_vision or []
    metadata_vision = metadata_vision or {}

    ai_cfg = (config.get("ai") or {})
    filename_style = ai_cfg.get("filename_style", "semantic-kebab")

    classification_cfg = (config.get("classification") or {})
    categories = classification_cfg.get("categories", [])
    category_names = [c.get("name", "other") for c in categories]

    prompt = f"""
You are Smart Sorter V5 running on Gemini 2.0 Flash.

You must:
1. Classify the document into ONE of these categories: {category_names}
2. Provide a confidence score between 0 and 1.
3. Provide a short reasoning string.
4. Suggest a semantic filename using style "{filename_style}".
5. Return STRICT JSON only.

Input filename: {filename}

Vision metadata:
{json.dumps(metadata_vision, ensure_ascii=False, indent=2)}

Document text:
\"\"\"{(text or '')[:4000]}\"\"\"

JSON response shape:
{{
  "text": "string",
  "category": "string",
  "confidence": 0.0,
  "metadata": {{}},
  "tables": [],
  "filename": "string",
  "reasoning": "string"
}}
"""

    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content(prompt)

    try:
        data = json.loads(resp.text)
    except Exception as e:
        log(f"[AI] Gemini JSON parse failed: {e}", "error")
        return {}

    # Defaults
    data.setdefault("text", text or "")
    data.setdefault("category", "other")
    data.setdefault("confidence", 0.0)
    data.setdefault("metadata", {})
    data.setdefault("tables", [])
    data.setdefault("filename", filename)
    data.setdefault("reasoning", "")

    return data

# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------
COLOR_MAP = {
    "success": "\033[92m",
    "error": "\033[91m",
    "warn": "\033[93m",
    "diag": "\033[96m",
    "info": "\033[97m",
    "reset": "\033[0m",
}

def log(msg: str, level: str = "info"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = COLOR_MAP.get(level, COLOR_MAP["info"])
    reset = COLOR_MAP["reset"]
    print(f"{color}[{level.upper()}] {ts} {msg}{reset}")

# ---------------------------------------------------------
# TEXT EXTRACTION
# ---------------------------------------------------------
def clean_extracted_text(text: str) -> str:
    lines = text.splitlines()
    cleaned = [line.strip() for line in lines if line.strip()]
    return "\n".join(cleaned)

def extract_text_generic(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()

    if ext in [".txt", ".md", ".log", ".csv"]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return ""

    if ext == ".docx":
        try:
            doc = docx.Document(path)
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return clean_extracted_text("\n".join(parts))
        except Exception:
            return ""

    if ext == ".pdf":
        try:
            doc = fitz.open(path)
            texts = [page.get_text("text") for page in doc]
            doc.close()
            return clean_extracted_text("\n".join(texts))
        except Exception:
            return ""

    if ext == ".xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            parts = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                parts.append(f"### SHEET: {sheet} ###")
                for row in ws.iter_rows(values_only=True):
                    vals = [str(v).strip() for v in row if v is not None]
                    if vals:
                        parts.append(" | ".join(vals))
            return clean_extracted_text("\n".join(parts))
        except Exception:
            return ""

    return ""

# ---------------------------------------------------------
# IMAGE → CLEAN PDF
# ---------------------------------------------------------
def convert_image_to_clean_pdf(image_path: str, log) -> str:
    base, _ = os.path.splitext(image_path)
    pdf_path = base + "_cleaned.pdf"

    try:
        img = Image.open(image_path).convert("RGB")
        img_np = np.array(img)

        if img_np.ndim == 3 and HAS_CV2:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            bw = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                35, 10
            )
            Image.fromarray(bw).save(pdf_path, "PDF", resolution=300)
        else:
            img.convert("L").save(pdf_path, "PDF", resolution=300)

        log(f"[PDF] Converted to cleaned PDF: {pdf_path}", "diag")
        return pdf_path

    except Exception as e:
        log(f"[PDF] Conversion failed: {e}", "warn")
        return image_path

# ---------------------------------------------------------
# RENDER-SAFE CLASSIFICATION ENTRYPOINT
# ---------------------------------------------------------
def process_file_for_web(path: str, config: dict) -> dict:
    """
    This is the ONLY entrypoint your Flask dashboard should call.
    It returns a dict with:
      - category
      - confidence
      - summary
      - final_filename
    """
    try:
        result = _classify_and_route_internal(path, config)
        return result or {"status": "Failed"}
    except Exception as e:
        log(f"[WEB] Error: {e}", "error")
        return {"status": "Failed", "summary": str(e)}

# ---------------------------------------------------------
# INTERNAL PIPELINE (same as V5, minus watchers)
# ---------------------------------------------------------
def _classify_and_route_internal(path: str, config: dict):
    if not os.path.exists(path):
        return {"status": "Failed", "summary": "File missing"}

    original_name = os.path.basename(path)
    ext = os.path.splitext(original_name)[1].lower()

    classification_cfg = (config.get("classification") or {})
    photo_exts = [e.lower() for e in classification_cfg.get("photo_extensions", [])]
    video_exts = [e.lower() for e in classification_cfg.get("video_extensions", [])]

    # Metadata
    try:
        stat = os.stat(path)
        metadata_fs = {
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
    except Exception:
        metadata_fs = {}

    # Defaults
    category = "other"
    confidence = 0.0
    ai_filename = None
    text = ""
    extracted_text = ""
    metadata = dict(metadata_fs)
    reasoning = ""
    treat_as_document = False

    classification_path = path
    storage_path = path

    # XLSX always document
    if ext == ".xlsx":
        treat_as_document = True

    # PHOTO DETECTION
    if ext in photo_exts:
        treat_as_document = False  # simplified for Render
        if not treat_as_document:
            category = "photos"
            confidence = 1.0
            ai_filename = original_name

    # VIDEO DETECTION
    elif ext in video_exts:
        category = "videos"
        confidence = 1.0
        ai_filename = original_name

    # DOCUMENT-PHOTO → PDF
    if ext in photo_exts and treat_as_document:
        storage_path = convert_image_to_clean_pdf(path, log)
        classification_path = path

    # NON-PHOTO DOCUMENT
    if ext not in photo_exts:
        extracted_text = extract_text_generic(classification_path)

    # GEMINI CLASSIFICATION
    gemini_result = gemini_process_document(
        path=classification_path,
        text=extracted_text,
        filename=original_name,
        config=config,
        log=log,
    )

    if gemini_result:
        text = gemini_result.get("text", "") or extracted_text
        category = gemini_result.get("category", "other")
        confidence = float(gemini_result.get("confidence", 0.0))
        metadata_ai = gemini_result.get("metadata") or {}
        ai_filename = gemini_result.get("filename") or original_name
        reasoning = gemini_result.get("reasoning", "")

        from metadata_enhancer import enhance_metadata
        metadata = enhance_metadata(
            text=text,
            metadata_ai=metadata_ai,
            metadata_vision={},
            metadata_fs=metadata_fs
        )

    # FALLBACK FILENAME
    if not ai_filename:
        ai_filename = generate_filename(
            text=text,
            category=category,
            original_filename=original_name,
            metadata=metadata,
        )

    # SMART MODE
    result_for_smart = {
        "category": category,
        "confidence": confidence,
        "metadata": metadata,
        "text": text,
    }
    final_category = smart_mode_v2(result_for_smart, log) or category

    # ROUTING
    result_for_router = {
        "category": final_category,
        "confidence": confidence,
        "metadata": metadata,
        "text": text,
        "filename": ai_filename,
    }

    final_filename = generate_final_filename(result_for_router, storage_path, log)
    destination = route_file(final_category, final_filename, config, log)

    # MOVE FILE
    try:
        shutil.move(storage_path, destination)
    except Exception as e:
        log(f"[MOVE] Failed: {e}", "error")

    # DASHBOARD EVENT
    add_event({
        "original": original_name,
        "category": final_category,
        "confidence": confidence,
        "final_filename": final_filename,
        "metadata": metadata,
        "reasoning": reasoning,
        "text": text,
    })

    return {
        "status": "Completed",
        "category": final_category,
        "confidence": confidence,
        "summary": reasoning or text[:200],
        "final_filename": final_filename,
    }



