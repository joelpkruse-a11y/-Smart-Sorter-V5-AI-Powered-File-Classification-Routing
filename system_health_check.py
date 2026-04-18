# ============================================================
# system_health_check.py — Smart Sorter V5.3
# Full Environment Diagnostic
# ============================================================

import os
import json
import shutil
from pathlib import Path

from utils.logging_utils import log_info, log_warn, log_error, log_diag
from utils.file_utils import ensure_folder
from smart_sorter_v5 import CONFIG


# ============================================================
# CHECK: FOLDERS
# ============================================================

def check_folders():
    log_info("=== Checking Folders ===")

    folders = [
        CONFIG.get("input_folder"),
        CONFIG.get("output_folder"),
        CONFIG.get("error_folder"),
        CONFIG.get("destinations", {}).get("sorted_root"),
    ]

    # Add all destination folders
    for key, path in CONFIG.get("destinations", {}).items():
        folders.append(path)

    for folder in folders:
        if not folder:
            continue

        p = Path(folder)
        try:
            ensure_folder(p)
            if p.exists():
                log_info(f"[OK] Folder exists: {p}")
            else:
                log_warn(f"[WARN] Folder missing: {p}")
        except Exception as e:
            log_error(f"[ERROR] Failed to validate folder {p}: {e}")


# ============================================================
# CHECK: CONFIG.JSON
# ============================================================

def check_config():
    log_info("=== Checking config.json ===")

    required_keys = ["input_folder", "output_folder", "error_folder", "destinations"]

    for key in required_keys:
        if key not in CONFIG:
            log_error(f"[ERROR] Missing config key: {key}")
        else:
            log_info(f"[OK] Config key present: {key}")


# ============================================================
# CHECK: GEMINI API KEY
# ============================================================

def check_gemini_key():
    log_info("=== Checking Gemini API Key ===")

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        log_warn("[WARN] GEMINI_API_KEY is NOT set.")
    else:
        log_info("[OK] GEMINI_API_KEY is set.")


# ============================================================
# CHECK: PYTHON MODULES
# ============================================================

def check_python_modules():
    log_info("=== Checking Python Modules ===")

    modules = {
        "PIL (Pillow)": "PIL",
        "PyMuPDF": "fitz",
        "Tesseract (pytesseract)": "pytesseract",
        "imagehash": "imagehash",
        "google-genai": "google.genai",
    }

    for name, module in modules.items():
        try:
            __import__(module)
            log_info(f"[OK] Module available: {name}")
        except Exception:
            log_warn(f"[WARN] Missing module: {name}")


# ============================================================
# CHECK: TESSERACT INSTALLATION
# ============================================================

def check_tesseract_install():
    log_info("=== Checking Tesseract Installation ===")

    exe = shutil.which("tesseract")
    if exe:
        log_info(f"[OK] Tesseract found: {exe}")
    else:
        log_warn("[WARN] Tesseract NOT found in PATH.")


# ============================================================
# CHECK: PHOTO DUPLICATE INDEX
# ============================================================

def check_photo_index():
    log_info("=== Checking Photo Duplicate Index ===")

    index_path = Path("C:/SmartInbox/photo_index.json")

    if not index_path.exists():
        log_warn("[WARN] photo_index.json does not exist yet.")
        return

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "phashes" in data or "filenames" in data:
            log_info("[OK] photo_index.json loaded successfully.")
        else:
            log_warn("[WARN] photo_index.json missing expected keys.")

    except Exception as e:
        log_error(f"[ERROR] Failed to read photo_index.json: {e}")


# ============================================================
# CHECK: LOGGING SYSTEM
# ============================================================

def check_logging():
    log_info("=== Checking Logging System ===")

    log_file = Path("C:/SmartInbox/System/sorter.log")

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("HEALTH CHECK: Logging OK\n")

        log_info(f"[OK] Logging file writable: {log_file}")

    except Exception as e:
        log_error(f"[ERROR] Logging file not writable: {e}")


# ============================================================
# RUN ALL CHECKS
# ============================================================

def run_health_check():
    log_info("============================================================")
    log_info("SMART SORTER V5.3 — SYSTEM HEALTH CHECK")
    log_info("============================================================")

    check_config()
    check_folders()
    check_gemini_key()
    check_python_modules()
    check_tesseract_install()
    check_photo_index()
    check_logging()

    log_info("============================================================")
    log_info("HEALTH CHECK COMPLETE")
    log_info("============================================================")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_health_check()