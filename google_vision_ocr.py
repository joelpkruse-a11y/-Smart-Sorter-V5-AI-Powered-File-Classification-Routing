import io
import traceback

def extract_text_google_vision(path, log):
    """
    Google Vision OCR for images.
    Returns dict with keys: text, ocr_confidence, metadata, tables.
    """

    try:
        from google.cloud import vision
    except Exception as e:
        log(f"[OCR] GV import failed ({e})", "warn")
        return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}

    try:
        client = vision.ImageAnnotatorClient()

        with open(path, "rb") as f:
            content = f.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)

        if response.error.message:
            log(f"[OCR] GV error: {response.error.message}", "warn")
            return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}

        annotations = response.text_annotations
        if not annotations:
            return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}

        full_text = annotations[0].description or ""
        confidence = None

        if hasattr(response, "full_text_annotation"):
            blocks = response.full_text_annotation.pages
            confs = []
            for page in blocks:
                for block in page.blocks:
                    if block.confidence:
                        confs.append(block.confidence)
            if confs:
                confidence = sum(confs) / len(confs)

        return {
            "text": full_text,
            "ocr_confidence": confidence,
            "metadata": {},
            "tables": []
        }

    except Exception as e:
        log(f"[OCR] GV image OCR failed ({e})", "warn")
        return {"text": "", "ocr_confidence": None, "metadata": {}, "tables": []}