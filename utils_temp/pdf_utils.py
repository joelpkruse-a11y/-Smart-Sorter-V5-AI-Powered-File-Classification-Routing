# ============================================================
# utils/pdf_utils.py
# High‑quality PDF conversion for Smart Sorter V5.4
# - Converts document‑photos to clean 600‑DPI PDFs
# - Auto-crops (tight), deskews, denoises, normalizes background
# - Safe fallback behavior
# ============================================================

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter


def _auto_crop_single_page(img_cv):
    """
    Bulletproof auto-crop (C3):
      - Canny edges
      - Adaptive threshold
      - Combined mask
      - Page-shape scoring
      - Minimum area threshold
      - Full-image fallback
    Returns cropped cv2 image.
    """
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape

    # --- 1) Canny edges ---
    edges = cv2.Canny(gray, 60, 180)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=2)

    # --- 2) Adaptive threshold ---
    adapt = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31, 15
    )

    # --- 3) Combine both ---
    combined = cv2.bitwise_or(edges, adapt)

    # --- 4) Find contours ---
    contours, _ = cv2.findContours(
        combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return img_cv  # fallback

    # --- 5) Score contours by "page-likeness" ---
    best_score = -1
    best_rect = None

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h

        # Reject tiny contours (< 30% of image area)
        if area < (H * W * 0.30):
            continue

        aspect = w / float(h)
        aspect_score = 1.0 - abs(aspect - (W / float(H)))  # closer to image aspect = better

        area_score = area / float(H * W)  # bigger = better

        # Combined score
        score = (0.7 * area_score) + (0.3 * aspect_score)

        if score > best_score:
            best_score = score
            best_rect = (x, y, w, h)

    # --- 6) If no valid contour found → fallback to full image ---
    if best_rect is None:
        return img_cv

    x, y, w, h = best_rect

    # --- 7) Final safety: if crop is still too small, fallback ---
    if w < W * 0.5 or h < H * 0.5:
        return img_cv

    # --- 8) Tight crop ---
    return img_cv[y:y+h, x:x+w]

# ------------------------------------------------------------
# Deskew using OpenCV
# ------------------------------------------------------------
def _deskew_image_cv(img_cv):
    """
    Deskew an image using OpenCV's minAreaRect angle detection.
    Returns a rotated image (cv2 format).
    """
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)

    thresh = cv2.threshold(
        gray, 0, 255,
        cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )[1]

    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return img_cv  # fallback

    angle = cv2.minAreaRect(coords)[-1]

    # Correct angle
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    (h, w) = img_cv.shape[:2]
    center = (w // 2, h // 2)

    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        img_cv, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated


# ------------------------------------------------------------
# Clean + normalize image for OCR
# ------------------------------------------------------------
def _clean_image_for_pdf(pil_img):
    """
    Apply light denoising, contrast boost, and background normalization.
    """
    # Convert to grayscale
    gray = pil_img.convert("L")

    # Slight contrast enhancement
    gray = ImageOps.autocontrast(gray)

    # Light denoise
    gray = gray.filter(ImageFilter.MedianFilter(size=3))

    # Normalize background
    np_img = np.array(gray)
    np_img = cv2.fastNlMeansDenoising(np_img, None, 10, 7, 21)

    return Image.fromarray(np_img)


# ------------------------------------------------------------
# Convert image → clean 600‑DPI PDF (with tight auto‑crop)
# ------------------------------------------------------------
def convert_image_to_clean_pdf(image_path: Path) -> Path | None:
    """
    Converts a document-photo into a clean 600‑DPI PDF.
    Now includes:
      - Tight auto-crop (Option A1)
      - Deskew
      - Cleaning + normalization
    Returns the PDF path or None on failure.
    """
    try:
        # Load image with OpenCV
        img_cv = cv2.imread(str(image_path))
        if img_cv is None:
            return None

        # 1) Auto-crop (tight)
        img_cv = _auto_crop_single_page(img_cv)

        # 2) Deskew
        img_cv = _deskew_image_cv(img_cv)

        # Convert to PIL
        pil_img = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))

        # 3) Clean + normalize
        cleaned = _clean_image_for_pdf(pil_img)

        # Output path
        pdf_path = image_path.with_suffix(".pdf")

        # 600 DPI PDF
        cleaned.save(
            pdf_path,
            "PDF",
            resolution=600,
            optimize=True,
        )

        return pdf_path

    except Exception:
        return None