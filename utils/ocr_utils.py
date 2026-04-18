# ============================================================
# ocr_utils.py — Smart Sorter V5.4
# Gemini 2.5 Flash Image OCR + Native PyMuPDF + Tesseract fallback
# ============================================================

import io
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
from PIL import Image
import pytesseract

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

import docx
import openpyxl

from utils.logging_utils import (
    log_info,
    log_warn,
    log_error,
    log_diag,
)

# ============================================================
# GEMINI OCR CLIENT
# ============================================================

try:
    if genai:
        OCR_CLIENT = genai.Client()
        log_diag("[OCR] Gemini Flash Image client initialized.")
    else:
        OCR_CLIENT = None
except Exception as e:
    OCR_CLIENT = None
    log_error(f"[OCR] Failed to initialize Gemini Flash Image: {e}")


# ============================================================
# PDF → IMAGE CONVERSION
# ============================================================

def pdf_to_images(path: Path, dpi: int = 300) -> List[Image.Image]:
    pages = []
    try:
        doc = fitz.open(path)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pages.append(img)
    except Exception as e:
        log_error(f"[OCR] PDF to Image conversion failed for {path.name}: {e}")
    return pages


# ============================================================
# OCR HELPER FUNCTIONS
# ============================================================

def tesseract_ocr(img: Image.Image) -> str:
    """Fallback OCR using standard Tesseract."""
    try:
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        log_error(f"[OCR] Tesseract OCR failed: {e}")
        return ""

def gemini_ocr_image(img: Image.Image, strict: bool = True) -> str:
    """Uses Gemini 2.5 Flash to extract text from an image."""
    if not OCR_CLIENT:
        return ""

    try:
        prompt = "Extract all text from this image accurately."
        if strict:
            prompt += " Do not hallucinate or add any text that is not explicitly present. Output ONLY the raw text."

        response = OCR_CLIENT.models.generate_content(
            model='gemini-2.5-flash',
            contents=[img, prompt],
        )
        return response.text.strip() if response.text else ""
    except Exception as e:
        log_warn(f"[OCR] Gemini OCR attempt failed: {e}")
        return ""


# ============================================================
# MASTER EXTRACTOR — USED BY SMART SORTER
# ============================================================

def extract_text_for_ai(filepath: str | Path) -> str:
    """
    Unified text extraction entry point.
    Smart Sorter main orchestrator calls ONLY this function.
    """
    path = Path(filepath)
    suffix = path.suffix.lower()
    
    log_diag(f"[OCR] Running extract_text_for_ai() on {path.name} (Type: {suffix})")

    # --------------------------------------------------------
    # PDF FILES (Hybrid: Native Text -> Scanned Image OCR)
    # --------------------------------------------------------
    if suffix == ".pdf":
        log_diag(f"[OCR] Attempting native text extraction for {path.name}")
        
        # 1. Native PyMuPDF Extraction (Token Saver)
        try:
            doc = fitz.open(path)
            native_text = "\n".join([page.get_text() for page in doc])
            
            # If we find more than 50 characters, it's a true digital PDF. 
            # We skip the AI/Image OCR completely.
            if len(native_text.strip()) > 50:
                log_info(f"[OCR] Native PDF text found ({len(native_text)} chars). Skipping Gemini OCR.")
                return native_text.strip()
            else:
                log_diag("[OCR] PDF lacks native text (likely a scan). Falling back to Image OCR.")
        except Exception as e:
            log_warn(f"[OCR] Native PDF extraction failed: {e}. Falling back to Image OCR.")

        # 2. Scanned PDF Fallback (Gemini -> Tesseract)
        pages = pdf_to_images(path)
        if not pages:
            return ""

        all_text = []
        for idx, page_img in enumerate(pages, start=1):
            log_diag(f"[OCR] Strict OCR request → Gemini 2.5 Flash Image (Page {idx})")
            text = gemini_ocr_image(page_img, strict=True)
            
            if not text:
                log_diag(f"[OCR] Flex OCR request → Gemini 2.5 Flash Image (Page {idx})")
                text = gemini_ocr_image(page_img, strict=False)

            if not text:
                log_warn(f"[OCR] Gemini OCR returned no text for Page {idx} — Tesseract fallback required.")
                text = tesseract_ocr(page_img)

            all_text.append(text)

        combined = "\n\n".join(all_text).strip()
        log_info(f"[OCR] PDF Scanned OCR extracted {len(combined)} chars")
        return combined

    # --------------------------------------------------------
    # MICROSOFT WORD (.DOCX)
    # --------------------------------------------------------
    elif suffix == ".docx":
        try:
            doc = docx.Document(path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            log_info(f"[OCR] DOCX extracted {len(text)} chars")
            return text.strip()
        except Exception as e:
            log_error(f"[OCR] DOCX extraction failed: {e}")
            return ""

    # --------------------------------------------------------
    # MICROSOFT EXCEL (.XLSX)
    # --------------------------------------------------------
    elif suffix == ".xlsx":
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
            lines = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    row_text = " | ".join([str(cell) for cell in row if cell is not None])
                    if row_text:
                        lines.append(row_text)
            text = "\n".join(lines)
            log_info(f"[OCR] XLSX extracted {len(text)} chars")
            return text.strip()
        except Exception as e:
            log_error(f"[OCR] XLSX extraction failed: {e}")
            return ""

    # --------------------------------------------------------
    # PLAIN TEXT / MARKDOWN (.TXT, .MD)
    # --------------------------------------------------------
    elif suffix in [".txt", ".md"]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            log_info(f"[OCR] TXT/MD extracted {len(text)} chars")
            return text.strip()
        except Exception as e:
            log_error(f"[OCR] TXT extraction failed: {e}")
            return ""

    # --------------------------------------------------------
    # IMAGES (.PNG, .JPG, .JPEG)
    # --------------------------------------------------------
    elif suffix in [".png", ".jpg", ".jpeg", ".heic", ".webp"]:
        try:
            img = Image.open(path).convert("RGB")
            
            log_diag("[OCR] Strict OCR request → Gemini 2.5 Flash Image")
            text = gemini_ocr_image(img, strict=True)
            
            if not text:
                log_diag("[OCR] Flex OCR request → Gemini 2.5 Flash Image")
                text = gemini_ocr_image(img, strict=False)

            if not text:
                log_warn("[OCR] Gemini OCR returned no text — Tesseract fallback required.")
                text = tesseract_ocr(img)

            log_info(f"[OCR] Image extracted {len(text)} chars")
            return text.strip()
            
        except Exception as e:
            log_error(f"[OCR] Image OCR failed completely: {e}")
            return ""

    # --------------------------------------------------------
    # UNSUPPORTED FILE TYPES
    # --------------------------------------------------------
    else:
        log_warn(f"[OCR] Unsupported file type for extraction: {suffix}")
        return ""