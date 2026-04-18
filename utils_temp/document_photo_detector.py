# ============================================================
# document_photo_detector.py — Smart Sorter V5.3
# Detects whether an image is a photo of a document
# ============================================================

from google import genai
from google.genai import types
from utils.logging_utils import log_diag, log_warn

try:
    DOC_CLIENT = genai.Client()
except Exception as e:
    DOC_CLIENT = None
    log_warn(f"[DOC-DETECT] Failed to initialize Gemini client: {e}")


def is_document_photo(img_bytes: bytes) -> bool:
    """
    Uses Gemini 2.5 Flash Image to determine if an image is a photo of a document.
    Returns True if the image contains a document (form, bill, letter, receipt, etc.)
    """
    if not DOC_CLIENT:
        log_warn("[DOC-DETECT] No Gemini client available.")
        return False

    prompt = (
        "Is this image a photo of a document (like a bill, tax form, letter, receipt, "
        "statement, contract, or printed page)? Respond ONLY with 'yes' or 'no'."
    )

    try:
        result = DOC_CLIENT.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt,
            ],
        )

        answer = (result.text or "").strip().lower()
        log_diag(f"[DOC-DETECT] Gemini response: {answer}")

        return answer.startswith("y")

    except Exception as e:
        log_warn(f"[DOC-DETECT] Detection failed: {e}")
        return False