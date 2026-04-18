# ============================================================
# deskew_denoise.py — Smart Sorter V5.3
# High-quality deskew + denoise for document photos
# ============================================================

import cv2
import numpy as np
from utils.logging_utils import log_diag, log_warn


def deskew_image(gray):
    """
    Automatically deskews a grayscale image using OpenCV.
    """
    try:
        # Threshold to get binary image
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find coordinates of all pixels > 0
        coords = np.column_stack(np.where(thresh > 0))
        angle = cv2.minAreaRect(coords)[-1]

        # Correct angle
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        log_diag(f"[DESKEW] Angle detected: {angle:.2f} degrees")

        # Rotate image
        (h, w) = gray.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        deskewed = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        return deskewed

    except Exception as e:
        log_warn(f"[DESKEW] Failed: {e}")
        return gray


def denoise_image(gray):
    """
    Removes noise and smooths background while preserving text.
    """
    try:
        # Light Gaussian blur to reduce grain
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # Adaptive threshold for crisp text
        cleaned = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            11,
        )

        return cleaned

    except Exception as e:
        log_warn(f"[DENOISE] Failed: {e}")
        return gray