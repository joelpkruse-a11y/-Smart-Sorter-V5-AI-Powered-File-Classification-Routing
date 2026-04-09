import os
import re
import logging
from werkzeug.utils import secure_filename

# PDF / DOCX / IMAGE extraction
from pdfminer.high_level import extract_text as pdf_extract_text
from docx import Document
from PIL import Image
import pytesseract

# Allowed extensions for uploads
ALLOWED_EXTENSIONS = {
    "pdf", "docx", "txt", "png", "jpg", "jpeg", "tiff", "bmp", "gif"
}

# ---------------------------------------------------------
# LOGGING HELPER (Smart Sorter V5 expects this)
# ---------------------------------------------------------
def log(message: str):
    """
    Simple logging helper used by Smart Sorter V5.
    Prints messages with a consistent prefix.
    """
    print(f"[SMART SORTER] {message}")


# ---------------------------------------------------------
# 1. EXTENSION VALIDATION
# ---------------------------------------------------------
def allowed_file(filename: str) -> bool:
    """
    Returns True if the file extension is allowed.
    """
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# ---------------------------------------------------------
# 2. FILENAME SANITIZATION
# ---------------------------------------------------------
def sanitize_filename(filename: str) -> str:
    """
    Cleans filenames to avoid unsafe characters.
    Uses Werkzeug's secure_filename + extra cleanup.
    """
    cleaned = secure_filename(filename)

    # Remove repeated underscores, stray dots, etc.
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("._ ")

    if not cleaned:
        cleaned = "file"

    return cleaned


# ---------------------------------------------------------
# 3. TEXT EXTRACTION ROUTER
# ---------------------------------------------------------
def extract_text(filepath: str) -> str:
    """
    Extracts text from PDF, DOCX, TXT, or image files.
    Returns extracted text or an empty string on failure.
    """
    ext = filepath.rsplit(".", 1)[1].lower()

    try:
        if ext == "pdf":
            return extract_pdf_text(filepath)

        elif ext == "docx":
            return extract_docx_text(filepath)

        elif ext == "txt":
            return extract_txt_text(filepath)

        elif ext in {"png", "jpg", "jpeg", "tiff", "bmp", "gif"}:
            return extract_image_text(filepath)

        else:
            logging.warning(f"[utils] Unsupported extension for text extraction: {ext}")
            return ""

    except Exception as e:
        logging.error(f"[utils] Error extracting text from {filepath}: {e}")
        return ""


# ---------------------------------------------------------
# 4. PDF TEXT EXTRACTION
# ---------------------------------------------------------
def extract_pdf_text(filepath: str) -> str:
    """
    Extracts text from a PDF using pdfminer.six.
    """
    try:
        text = pdf_extract_text(filepath)
        return text or ""
    except Exception as e:
        logging.error(f"[utils] PDF extraction failed: {e}")
        return ""


# ---------------------------------------------------------
# 5. DOCX TEXT EXTRACTION
# ---------------------------------------------------------
def extract_docx_text(filepath: str) -> str:
    """
    Extracts text from a DOCX file using python-docx.
    """
    try:
        doc = Document(filepath)
        text = "\n".join([p.text for p in doc.paragraphs])
        return text or ""
    except Exception as e:
        logging.error(f"[utils] DOCX extraction failed: {e}")
        return ""


# ---------------------------------------------------------
# 6. TXT TEXT EXTRACTION
# ---------------------------------------------------------
def extract_txt_text(filepath: str) -> str:
    """
    Reads plain text files safely.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logging.error(f"[utils] TXT extraction failed: {e}")
        return ""


# ---------------------------------------------------------
# 7. IMAGE OCR EXTRACTION
# ---------------------------------------------------------
def extract_image_text(filepath: str) -> str:
    """
    Extracts text from images using Tesseract OCR.
    """
    try:
        img = Image.open(filepath)
        text = pytesseract.image_to_string(img)
        return text or ""
    except Exception as e:
        logging.error(f"[utils] OCR extraction failed: {e}")
        return ""

