# ============================================================
# initial_scan.py — Smart Sorter V5.3
# One-Time Deep Scan of Observer Groups
# ============================================================

import time
from pathlib import Path

from utils.logging_utils import log_info, log_warn, log_error, log_diag
from utils.file_utils import is_file_stable
from smart_sorter_v5 import process_file, CONFIG


# ============================================================
# LOAD OBSERVER GROUPS
# ============================================================

OBSERVER_GROUPS = CONFIG.get("observer_groups", {})
INITIAL_SCAN_GROUPS = CONFIG.get("initial_scan_groups", [])
FILE_READINESS_CFG = CONFIG.get("file_readiness", {})


# ============================================================
# SCAN A SINGLE FOLDER
# ============================================================

def scan_folder(folder: Path):
    """
    Scans a folder and processes all files inside it.
    """
    if not folder.exists():
        log_warn(f"[SCAN] Folder does not exist: {folder}")
        return

    log_info(f"[SCAN] Scanning folder: {folder}")

    try:
        for item in folder.iterdir():
            if not item.is_file():
                continue

            # Ensure file is stable before processing
            if not is_file_stable(item, FILE_READINESS_CFG):
                log_warn(f"[SCAN] File not stable, skipping: {item.name}")
                continue

            log_diag(f"[SCAN] Processing: {item.name}")
            process_file(item)

    except Exception as e:
        log_error(f"[SCAN] Error scanning folder {folder}: {e}")


# ============================================================
# RUN INITIAL SCAN
# ============================================================

def run_initial_scan():
    """
    Runs a one-time deep scan of all configured observer groups.
    """
    log_info("============================================================")
    log_info("[SCAN] Starting initial scan of observer groups...")
    log_info("============================================================")

    for group_name in INITIAL_SCAN_GROUPS:
        paths = OBSERVER_GROUPS.get(group_name, [])

        if not paths:
            log_warn(f"[SCAN] No paths defined for group: {group_name}")
            continue

        log_info(f"[SCAN] Group: {group_name}")

        for folder_str in paths:
            folder = Path(folder_str)
            scan_folder(folder)

    log_info("============================================================")
    log_info("[SCAN] Initial scan complete.")
    log_info("============================================================")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_initial_scan()