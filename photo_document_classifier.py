# ============================================================
# photo_document_classifier.py
# Smart Sorter V5.4 — Lighting-Agnostic Document Classifier
# ============================================================

import cv2
import numpy as np
from pathlib import Path

def _get_edge_density(img_cv: np.ndarray) -> float:
    """
    Calculates the percentage of pixels that are sharp edges.
    Documents (text, lines, borders) typically have higher edge 
    density than soft, natural photos.
    """
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    return float(np.mean(edges > 0))

def _get_aspect_ratio(img_cv: np.ndarray) -> float:
    """
    Calculates aspect ratio. Documents, receipts, and 
    screenshots typically have an aspect ratio > 1.25.
    """
    h, w = img_cv.shape[:2]
    if min(w, h) == 0:
        return 1.0
    return max(w, h) / min(w, h)

def classify_image(path: Path, gv_ocr: dict = None) -> str:
    """
    Classify an image as:
        - "photo"
        - "document_photo"

    Uses:
        - Google Vision OCR text length (Primary)
        - Aspect ratio (Secondary)
        - Edge density (Fallback)
        
    Note: Lighting/Brightness heuristics have been removed to 
    safely capture dark-mode screenshots and thermal receipts.
    """
    # --------------------------------------------------------
    # 1. Evaluate OCR Text Signal (The strongest indicator)
    # --------------------------------------------------------
    gv_ocr = gv_ocr or {}
    text = gv_ocr.get("text", "") or ""
    text_len = len(text.strip())

    # If the image contains significant text, it is undeniably a document.
    if text_len > 40:
        return "document_photo"

    # --------------------------------------------------------
    # 2. Image Geometry & Edge Fallbacks
    # --------------------------------------------------------
    try:
        img_cv = cv2.imread(str(path))
        if img_cv is None:
            return "photo"  # Fail safe to photo if OpenCV can't read it
            
        aspect_ratio = _get_aspect_ratio(img_cv)
        edge_density = _get_edge_density(img_cv)
        
        # Is it shaped like a phone screen, receipt, or 8.5x11 paper?
        is_rectangular = aspect_ratio > 1.25
        
        # Does it have sharp lines/text? (>5% of pixels are sharp edges)
        has_text_edges = edge_density > 0.05 
        
        # If it has a little bit of text (e.g., a tiny receipt header) AND a document shape
        if text_len > 15 and is_rectangular:
            return "document_photo"
            
        # If OCR completely failed, but it has the shape AND edge density of a document
        if is_rectangular and has_text_edges:
            return "document_photo"
            
    except Exception:
        pass # If any image math fails, safely fall through to "photo"

    # --------------------------------------------------------
    # 3. Default to Photo
    # --------------------------------------------------------
    return "photo"