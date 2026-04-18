# ============================================================
# utils.py — Smart Sorter V5 (Full Production Build)
# ============================================================

import os
import re
import sys
import datetime
from pathlib import Path

# OCR / Extraction
from pdf2image import convert_from_path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import pytesseract
from docx import Document

# ============================================================
# COLOR-CODED LOGGER (Windows-safe)
# ============================================================

RESET = "\033[0m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"

def _ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_info(msg):
    print(f"{GREEN}[INFO] {_ts()} {msg}{RESET}")

def log_warn(msg):
    print(f"{YELLOW}[WARN] {_ts()} {msg}{RESET}")

def log_error(msg):
    print(f"{RED}[ERROR] {_ts()} {msg}{RESET}", file=sys.stderr)

def log_diag(msg):
    print(f"{CYAN}[DIAG] {_ts()} {msg}{RESET}")

# ------------------------------------------------------------
# Backwards compatibility for legacy modules (filename_v3_engine, routing)
# ------------------------------------------------------------
def log(msg, level: str = "info"):
    """
    Compatibility wrapper for legacy modules.
    Supports:
        log("message")
        log("message", "warn")
        log("message", "error")
        log("message", "diag")
    """
    level = (level or "info").lower()

    if level == "warn":
        log_warn(msg)
    elif level == "error":
        log_error(msg)
    elif level in ("diag", "debug"):
        log_diag(msg)
    else:
        log_info(msg)

# ============================================================
# FILE EXTENSION VALIDATION
# ============================================================

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".txt",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"
}

def allowed_file(filename):
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_EXTENSIONS

# ============================================================
# FILENAME SANITIZATION
# ============================================================

def sanitize_filename(name):
    """
    Removes unsafe characters and collapses whitespace.
    """
    name = re.sub(r"[^\w\-. ]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

# ============================================================
# TEXT EXTRACTION — PDF
# ============================================================

def extract_text_from_pdf(filepath):
    """
    Converts PDF pages to images and OCRs them.
    """
    log_info(f"[OCR] Extracting text from PDF: {os.path.basename(filepath)}")

    try:
        pages = convert_from_path(filepath, dpi=400)
        log_diag(f"[OCR] Converted PDF to {len(pages)} image(s) at 400 DPI.")
    except Exception as e:
        log_error(f"[OCR] PDF conversion failed: {e}")
        return ""

    text_chunks = []

    for idx, page in enumerate(pages, start=1):
        log_diag(f"[OCR] OCRing PDF page {idx}/{len(pages)}")
        try:
            text = pytesseract.image_to_string(page)
            text_chunks.append(text)
        except Exception as e:
            log_error(f"[OCR] OCR failed on page {idx}: {e}")

    return "\n".join(text_chunks)

# ============================================================
# TEXT EXTRACTION — DOCX
# ============================================================

def extract_text_from_docx(filepath):
    log_info(f"[OCR] Extracting text from DOCX: {os.path.basename(filepath)}")
    try:
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        log_error(f"[OCR] DOCX extraction failed: {e}")
        return ""

# ============================================================
# TEXT EXTRACTION — TXT
# ============================================================

def extract_text_from_txt(filepath):
    log_info(f"[OCR] Extracting text from TXT: {os.path.basename(filepath)}")
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        log_error(f"[OCR] TXT extraction failed: {e}")
        return ""

# ============================================================
# TEXT EXTRACTION — IMAGE FILES
# ============================================================

def extract_text_from_image(filepath):
    log_info(f"[OCR] Extracting text from IMAGE: {os.path.basename(filepath)}")
    try:
        img = Image.open(filepath)
        return pytesseract.image_to_string(img)
    except Exception as e:
        log_error(f"[OCR] Image OCR failed: {e}")
        return ""

# ============================================================
# MASTER EXTRACTOR — USED BY SMART SORTER
# ============================================================

def extract_text_for_ai(filepath):
    """
    Unified text extraction entry point.
    Smart Sorter calls ONLY this function.
    """
    suffix = Path(filepath).suffix.lower()
    log_diag(f"[DEBUG] Running extract_text_for_ai()")
    log_diag(f"[DEBUG] suffix detected = '{suffix}' for {os.path.basename(filepath)}")

    if suffix == ".pdf":
        return extract_text_from_pdf(filepath)

    if suffix == ".docx":
        return extract_text_from_docx(filepath)

    if suffix == ".txt":
        return extract_text_from_txt(filepath)

    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}:
        return extract_text_from_image(filepath)

    log_warn(f"[OCR] Unsupported file type: {suffix}")
    return ""