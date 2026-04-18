# ============================================================
# vision_ocr.py — Smart Sorter V5.4
# Clean Google Cloud Vision API Wrapper
# ============================================================

import io
import traceback

def extract_text_google_vision(path, log):
    """
    Google Vision OCR for images.
    Returns dict with keys: text, ocr_confidence, metadata, tables.
    """
    # --------------------------------------------------------
    # 1. Attempt Import
    # --------------------------------------------------------
    try:
        from google.cloud import vision
    except ImportError as e:
        log(f"[OCR] Google Cloud Vision library not found. Is it installed in your venv? ({e})", "warn")
        return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}
    except Exception as e:
        log(f"[OCR] GV import failed ({e})", "warn")
        return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}

    # --------------------------------------------------------
    # 2. Call API & Parse
    # --------------------------------------------------------
    try:
        client = vision.ImageAnnotatorClient()

        with open(path, "rb") as f:
            content = f.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)

        # API-level error (e.g., bad credentials)
        if response.error.message:
            log(f"[OCR] GV API Error: {response.error.message}", "error")
            return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}

        annotations = response.text_annotations
        if not annotations:
            return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}

        full_text = annotations[0].description or ""
        confidence = None

        # Extract block-level confidence if available
        if hasattr(response, "full_text_annotation"):
            pages = response.full_text_annotation.pages
            confs = []
            for page in pages:
                for block in page.blocks:
                    if block.confidence is not None:
                        confs.append(block.confidence)
            if confs:
                confidence = sum(confs) / len(confs)

        return {
            "text": full_text.strip(),
            "ocr_confidence": confidence,
            "metadata": {},
            "tables": []
        }

    except Exception as e:
        log(f"[OCR] Google Vision extraction failed entirely: {e}", "error")
        log(traceback.format_exc(), "diag")
        return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}