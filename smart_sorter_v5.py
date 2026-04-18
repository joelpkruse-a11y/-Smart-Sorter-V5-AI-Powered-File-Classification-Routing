# ============================================================
# SMART SORTER V5.4 — MAIN ORCHESTRATOR (Gemini 2.5 Flash)
# Photos + Documents + Vision + PDF + Photo DB + Multi‑Page
# ============================================================

import os
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# ============================================================
# LOCAL MODULE IMPORTS
# ============================================================

from utils.logging_utils import log, log_info, log_warn, log_error, log_diag
from utils.ocr_utils import extract_text_for_ai
from utils.file_utils import ensure_folder, safe_move, is_file_stable

from utils.pdf_utils import convert_image_to_clean_pdf

from v3_debug_dashboard import start_dashboard

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ai.ai_engine import (
    analyze_with_gemini,
    classify_text,
    extract_metadata,
    summarize_text,
    run_full_retry_pipeline,
)

from filename_v3_engine import build_v3_filename
from filename_router import route_file
from photo_duplicates import is_photo_duplicate

from vision_ocr import extract_text_google_vision
from photo_document_classifier import classify_image
from photo_ingestion import ingest_photo
from document_ingestion import ingest_document

from multi_page_detector import (
    detect_multi_page_from_single,
    detect_multi_page_from_burst,
    group_burst_photos,
)

# ============================================================
# LOAD CONFIG
# ============================================================

CONFIG_PATH = Path("C:/SmartInbox/config.json")

if not CONFIG_PATH.exists():
    raise FileNotFoundError("config.json missing at C:/SmartInbox/config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

INPUT_FOLDER = Path(CONFIG.get("input_folder"))
OUTPUT_FOLDER = Path(CONFIG.get("output_folder"))
ERROR_FOLDER = Path(CONFIG.get("error_folder"))
FILE_READINESS_CFG = CONFIG.get("file_readiness", {})

ensure_folder(INPUT_FOLDER)
ensure_folder(OUTPUT_FOLDER)
ensure_folder(ERROR_FOLDER)

# Photo destination root (year/month subfolders will be created under this)
PHOTO_ROOT = Path(r"C:\Users\joelk\OneDrive\Smart Inbox\Incoming\Sorted\Photos")


# ============================================================
# HELPERS
# ============================================================

def _build_photo_destination(path: Path) -> Path:
    """
    Build destination path for a photo:
        Photos/<YEAR>/<MONTH>/<filename>
    """
    try:
        stat = path.stat()
        dt = datetime.fromtimestamp(stat.st_mtime)
    except Exception:
        dt = datetime.now()

    year = f"{dt.year:04d}"
    month = f"{dt.month:02d}"

    dest_dir = PHOTO_ROOT / year / month
    ensure_folder(dest_dir)
    return dest_dir / path.name

# ============================================================
# PROCESS A SINGLE FILE (V5.4 — Multi‑Page + 600 DPI)
# ============================================================

def process_file(path: Path):
    """
    Full pipeline:
        - File readiness
        - Multi‑page detection (document_photo only, BEFORE duplicates)
        - Duplicate detection (photos only)
        - Photo/Document classification (Vision OCR)
        - Optional PDF conversion for document-photos
        - OCR (for documents)
        - Gemini analysis
        - Semantic metadata extraction
        - Filename generation
        - Routing
        - Move file
        - Photo/Document DB ingestion
    """
    try:
        if not path.exists():
            return

        if "Duplicates" in str(path):
            return

        log_info(f"[PROCESS] Starting: {path.name}")

        # ----------------------------------------------------
        # 1) Ensure file is stable
        # ----------------------------------------------------
        if not is_file_stable(path, FILE_READINESS_CFG):
            log_warn(f"[PROCESS] File not stable, skipping: {path.name}")
            return

        suffix = path.suffix.lower()
        is_image = suffix in [".jpg", ".jpeg", ".png", ".heic", ".webp"]

        # ----------------------------------------------------
        # 2) Vision OCR (needed for classification)
        # ----------------------------------------------------
        gv_ocr = None
        if is_image:
            gv_ocr = extract_text_google_vision(str(path), log_diag)
            text_len = len((gv_ocr or {}).get("text", "") or "")
            conf = (gv_ocr or {}).get("ocr_confidence", None)
            log_diag(f"[GV] OCR len={text_len}, conf={conf}")

        # ----------------------------------------------------
        # 3) Photo vs Document classification
        # ----------------------------------------------------
        classification = None
        if is_image:
            classification = classify_image(path, gv_ocr)
            log_diag(f"[CLASSIFIER] Image classified as: {classification}")

        # ----------------------------------------------------
        # 4) Multi‑page detection (ONLY for document_photo)
        #     Runs BEFORE duplicate detection
        # ----------------------------------------------------
        if is_image and classification == "document_photo":
            log_diag("[MULTIPAGE] Checking for multi‑page content...")
            pdf = detect_multi_page_from_single(path)

            if pdf:
                log_info(f"[MULTIPAGE] Multi‑page PDF created: {pdf.name}")
                path = pdf
                is_image = False  # Now it's a PDF
                suffix = ".pdf"

        # ----------------------------------------------------
        # 5) Duplicate detection (photos only)
        # ----------------------------------------------------
        if is_image:
            is_dup, method = is_photo_duplicate(path)
            if is_dup:
                dup_folder = Path(r"C:\SmartInbox\Incoming\Duplicates")
                dup_folder.mkdir(parents=True, exist_ok=True)

                dest = dup_folder / path.name
                try:
                    shutil.move(path, dest)
                    log_info(f"[PROCESS] Duplicate detected ({method}), moved to {dest}")
                except Exception as e:
                    log_error(f"[PROCESS] Failed to move duplicate: {e}")

                return

        # ----------------------------------------------------
        # 6) PHOTO branch
        # ----------------------------------------------------
        if is_image and classification == "photo":
            dest = _build_photo_destination(path)
            safe_move(path, dest)

            try:
                ingest_photo(dest, CONFIG)
                log_diag(f"[PHOTO] Ingested into faces.db: {dest}")
            except Exception as e:
                log_warn(f"[PHOTO] Ingestion into faces.db failed: {e}")

            log_info(f"[PROCESS] Completed (photo): {dest}")
            return

        # ----------------------------------------------------
        # 7) DOCUMENT-PHOTO branch (single-page)
        #     Convert to clean 600‑DPI PDF
        # ----------------------------------------------------
        if is_image and classification == "document_photo":
            try:
                original_path = path
                pdf_path = convert_image_to_clean_pdf(path)

                if pdf_path:
                    log_diag(f"[PHOTO] Converted document-photo to PDF: {pdf_path}")
                    path = pdf_path

                    try:
                        original_path.unlink(missing_ok=True)
                        log_diag("[PHOTO] Deleted original image after PDF conversion")
                    except Exception as e:
                        log_warn(f"[PHOTO] Failed to delete original image: {e}")
                else:
                    log_warn("[PHOTO] PDF conversion failed; continuing with image")
            except Exception as e:
                log_warn(f"[PHOTO] Document-photo PDF conversion failed: {e}")

        # ----------------------------------------------------
        # 8) OCR (strict mode) — for documents
        # ----------------------------------------------------
        ocr_text = extract_text_for_ai(path)
        log_diag(f"[PROCESS] OCR extracted {len(ocr_text)} chars")

        # ----------------------------------------------------
        # 9) Gemini AI analysis (unified pipeline)
        # ----------------------------------------------------
        ai_result = run_full_retry_pipeline(
            analyze_with_gemini,
            path,
            ocr_text,
        )

        if not ai_result:
            log_warn(f"[PROCESS] AI returned no result, sending to error folder: {path.name}")
            safe_move(path, ERROR_FOLDER / path.name)
            return

        # Semantic metadata
        ai_summary = ai_result.get("summary") or ai_result.get("description") or ""
        ai_keywords = ai_result.get("keywords") or []
        ai_vector = ai_result.get("embedding") or []   # placeholder for semantic search

        log_diag(f"[AI] Summary: {ai_summary[:200]}...")

        # ----------------------------------------------------
        # 10) Build semantic filename
        # ----------------------------------------------------
        final_filename = build_v3_filename(
            ai_result,
            original_filename=path.name,
            ocr_text=ocr_text,
        )

        # ----------------------------------------------------
        # 11) Route file to destination folder
        # ----------------------------------------------------
        category = ai_result.get("category", "other")
        final_path = route_file(category, final_filename, CONFIG, log)

        # ----------------------------------------------------
        # 12) Move file
        # ----------------------------------------------------
        safe_move(path, final_path)

        # ----------------------------------------------------
        # 13) DOCUMENT INGESTION
        # ----------------------------------------------------
        try:
            ingest_document(final_path, CONFIG)
            log_diag(f"[DOC] Ingested into faces.db: {final_path}")
        except Exception as e:
            log_warn(f"[DOC] Document ingestion failed: {e}")

        log_info(f"[PROCESS] Completed (document): {final_path}")

    except Exception as e:
        log_error(f"[PROCESS] ERROR processing {path.name}: {e}")
        try:
            safe_move(path, ERROR_FOLDER / path.name)
        except Exception as e2:
            log_error(f"[PROCESS] Failed to move to error folder: {e2}")

# ============================================================
# WATCHER LOOP (Event-Driven via Watchdog)
# ============================================================

class SmartInboxHandler(FileSystemEventHandler):
    """Handles file system events for the input folder."""
    
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if "Duplicates" in str(path):
            return
        # Process the newly created file
        process_file(path)

    def on_moved(self, event):
        # Captures files that are cut/pasted or dragged into the folder
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if "Duplicates" in str(path):
            return
        # Process the moved file
        process_file(path)

def watcher_loop():
    log_info("[WATCHER] Smart Sorter V5.4 (Watchdog) started.")
    log_info(f"[WATCHER] Monitoring main folder: {INPUT_FOLDER}")

    # Build a list of all folders we need to watch/sweep based on Config.json
    all_watch_folders = [INPUT_FOLDER]
    observer_groups = CONFIG.get("observer_groups", {})
    
    for group_name, paths in observer_groups.items():
        for folder_str in paths:
            all_watch_folders.append(Path(folder_str))

    # 1. Initial Sweep: Catch any files that arrived while the script was off
    log_info("[WATCHER] Performing initial sweep of existing files...")
    for folder in all_watch_folders:
        if folder.exists():
            try:
                for item in folder.iterdir():
                    if item.is_file() and "Duplicates" not in str(item):
                        process_file(item)
            except Exception as e:
                log_error(f"[WATCHER] Error during initial sweep of {folder.name}: {e}")

    # 2. Set up the Watchdog Observer
    event_handler = SmartInboxHandler()
    observer = Observer()
    
    # Dynamically attach the observer to every folder in our list
    for folder in all_watch_folders:
        if folder.exists():
            observer.schedule(event_handler, str(folder), recursive=False)
            if folder != INPUT_FOLDER:
                log_info(f"[WATCHER] Also monitoring: {folder}")
        else:
            if folder != INPUT_FOLDER:
                log_warn(f"[WATCHER] Configured folder not found, skipping: {folder}")

    observer.start()

    # 3. Keep the main thread alive
    try:
        while True:
            time.sleep(1) 
    except KeyboardInterrupt:
        log_info("[WATCHER] Stopping observer (KeyboardInterrupt)...")
        observer.stop()
    except Exception as e:
        log_error(f"[WATCHER] Observer encountered a fatal error: {e}")
        observer.stop()
        
    observer.join()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    # --------------------------------------------------------
    # Start Smart Sorter Dashboard (v3_debug_dashboard)
    # --------------------------------------------------------
    try:
        start_dashboard(port=8765)
        log_info("[DASHBOARD] Smart Sorter Dashboard running on http://localhost:8765")
    except Exception as e:
        log_warn(f"[DASHBOARD] Failed to start dashboard: {e}")

    # --------------------------------------------------------
    # Start Photo Dashboard (photo_dashboard.py)
    # --------------------------------------------------------
    try:
        subprocess.Popen(
            ["C:\\SmartInbox\\.venv\\Scripts\\python.exe", "photo_dashboard.py"],
            cwd="C:\\SmartInbox"
        )
        log_info("[PHOTO-DASHBOARD] Running on http://localhost:5005")
    except Exception as e:
        log_warn(f"[PHOTO-DASHBOARD] Failed to start: {e}")

    # --------------------------------------------------------
    # Start watcher loop
    # --------------------------------------------------------
    watcher_loop()