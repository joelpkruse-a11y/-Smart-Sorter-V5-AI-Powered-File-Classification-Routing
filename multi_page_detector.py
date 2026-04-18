# ============================================================
# multi_page_detector.py
# Hybrid multi‑page detection for Smart Sorter V5.4
# - Detects multiple pages inside a single photo
# - Detects multi‑page bursts (multiple photos)
# - Gemini Vision → OpenCV fallback
# - Crops pages and builds 600‑DPI PDFs
# - Deletes original images after PDF creation
# ============================================================

import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from datetime import datetime
import json
import os
import shutil

# Optional Gemini Vision
try:
    from google import genai
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False


# ------------------------------------------------------------
# Gemini Vision page detection
# ------------------------------------------------------------
def detect_pages_gemini(image_path: Path):
    """
    Returns a list of bounding boxes:
    [
        {"page": 1, "bbox": [x1,y1,x2,y2]},
        ...
    ]
    or None if detection fails.
    """
    if not GEMINI_AVAILABLE:
        return None

    try:
        client = genai.Client()
        img_bytes = image_path.read_bytes()

        prompt = """
        Detect all document pages visible in this image.
        Return ONLY JSON like:
        [
          {"page": 1, "bbox": [x1,y1,x2,y2]},
          {"page": 2, "bbox": [x1,y1,x2,y2]}
        ]
        """

        result = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt, img_bytes],
        )

        text = result.text.strip()
        return json.loads(text)

    except Exception:
        return None


# ------------------------------------------------------------
# OpenCV fallback page detection
# ------------------------------------------------------------
def detect_pages_opencv(image_path: Path):
    """
    Detects multiple white rectangular regions (pages).
    Returns list of bounding boxes or None.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        21, 10
    )

    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    pages = []
    h, w = gray.shape

    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)

        # Filter out tiny or weird shapes
        if cw < w * 0.15 or ch < h * 0.15:
            continue

        aspect = ch / cw
        if 0.8 < aspect < 2.0:  # typical page ratio
            pages.append([x, y, x + cw, y + ch])

    if not pages:
        return None

    # Sort left→right, top→bottom
    pages = sorted(pages, key=lambda b: (b[1], b[0]))

    return [{"page": i + 1, "bbox": b} for i, b in enumerate(pages)]


# ------------------------------------------------------------
# Crop pages from bounding boxes
# ------------------------------------------------------------
def crop_pages(image_path: Path, page_boxes):
    """
    Returns list of cropped page image paths.
    """
    img = Image.open(image_path).convert("RGB")
    out_paths = []

    for p in page_boxes:
        x1, y1, x2, y2 = p["bbox"]
        crop = img.crop((x1, y1, x2, y2))

        out = image_path.parent / f"{image_path.stem}_page{p['page']}.jpg"
        crop.save(out, "JPEG", quality=95)
        out_paths.append(out)

    return out_paths


# ------------------------------------------------------------
# Build multi‑page PDF (600 DPI)
# ------------------------------------------------------------
def build_pdf(page_images, output_pdf: Path):
    imgs = [Image.open(p).convert("RGB") for p in page_images]
    imgs[0].save(
        output_pdf,
        "PDF",
        resolution=600,
        save_all=True,
        append_images=imgs[1:]
    )
    return output_pdf


# ------------------------------------------------------------
# Burst grouping for multiple photos
# ------------------------------------------------------------
def group_burst_photos(photo_paths, threshold_seconds=4):
    """
    Given a list of image paths, group them by capture time.
    Returns list of groups: [ [img1,img2], [img3], ... ]
    """
    def get_ts(p):
        try:
            return datetime.fromtimestamp(os.path.getmtime(p))
        except Exception:
            return None

    photos = sorted(photo_paths, key=lambda p: get_ts(p))
    groups = []
    current = []

    for p in photos:
        ts = get_ts(p)
        if not current:
            current.append(p)
            continue

        prev_ts = get_ts(current[-1])
        delta = (ts - prev_ts).total_seconds()

        if delta <= threshold_seconds:
            current.append(p)
        else:
            groups.append(current)
            current = [p]

    if current:
        groups.append(current)

    return groups


# ------------------------------------------------------------
# Main entry: detect multi‑page from single photo
# ------------------------------------------------------------
def detect_multi_page_from_single(image_path: Path):
    """
    Returns:
      - None → single page
      - Path to generated PDF → multi‑page
    Deletes original image(s) after PDF creation.
    """
    # 1. Try Gemini
    boxes = detect_pages_gemini(image_path)
    if boxes and len(boxes) > 1:
        pages = crop_pages(image_path, boxes)
        pdf_path = image_path.parent / f"{image_path.stem}_multipage.pdf"
        build_pdf(pages, pdf_path)

        # Delete originals
        try:
            image_path.unlink(missing_ok=True)
            for p in pages:
                p.unlink(missing_ok=True)
        except Exception:
            pass

        return pdf_path

    # 2. Try OpenCV fallback
    boxes = detect_pages_opencv(image_path)
    if boxes and len(boxes) > 1:
        pages = crop_pages(image_path, boxes)
        pdf_path = image_path.parent / f"{image_path.stem}_multipage.pdf"
        build_pdf(pages, pdf_path)

        # Delete originals
        try:
            image_path.unlink(missing_ok=True)
            for p in pages:
                p.unlink(missing_ok=True)
        except Exception:
            pass

        return pdf_path

    return None  # single page


# ------------------------------------------------------------
# Main entry: detect multi‑page from burst photos
# ------------------------------------------------------------
def detect_multi_page_from_burst(photo_paths):
    """
    Given a list of image paths from the same burst,
    assemble into a multi‑page PDF.
    Deletes originals after PDF creation.
    """
    if len(photo_paths) <= 1:
        return None

    pdf_path = Path(photo_paths[0]).parent / "burst_multipage.pdf"
    imgs = [Image.open(p).convert("RGB") for p in photo_paths]

    imgs[0].save(
        pdf_path,
        "PDF",
        resolution=600,
        save_all=True,
        append_images=imgs[1:]
    )

    # Delete originals
    for p in photo_paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass

    return pdf_path