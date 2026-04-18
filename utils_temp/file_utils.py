# ============================================================
# file_utils.py — Smart Sorter V5.3
# File Readiness • Safe Moves • Folder Utilities
# ============================================================

import os
import time
import shutil
from pathlib import Path
from typing import Dict, Any

from utils.logging_utils import log_info, log_warn, log_error, log_diag


# ============================================================
# FOLDER CREATION
# ============================================================

def ensure_folder(path: Path):
    """Ensures a folder exists."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log_error(f"[FILE] Failed to create folder {path}: {e}")


# ============================================================
# FILE READINESS CHECK
# ============================================================

def is_file_stable(path: Path, cfg: Dict[str, Any]) -> bool:
    """
    Ensures a file is fully written before processing.
    Uses:
        - size stability check
        - timeout
        - retry interval
    """
    timeout = cfg.get("timeout_seconds", 10)
    interval = cfg.get("stability_check_interval", 0.5)

    start = time.time()
    last_size = -1

    while True:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            log_warn(f"[FILE] File disappeared during readiness check: {path}")
            return False
        except Exception as e:
            log_warn(f"[FILE] Error checking file size: {e}")
            return False

        if size == last_size and size > 0:
            log_diag(f"[FILE] File stable: {path.name}")
            return True

        last_size = size

        if time.time() - start > timeout:
            log_warn(f"[FILE] Timeout waiting for file stability: {path.name}")
            return False

        time.sleep(interval)


# ============================================================
# SAFE MOVE (OneDrive‑Safe)
# ============================================================

def safe_move(src: Path, dst: Path):
    """
    Moves a file safely with retries.
    Handles:
        - OneDrive sync locks
        - Antivirus locks
        - Windows file handle delays
    """
    ensure_folder(dst.parent)

    for attempt in range(10):
        try:
            shutil.move(str(src), str(dst))
            log_info(f"[FILE] Moved → {dst}")
            return
        except PermissionError:
            log_warn(f"[FILE] Move locked (attempt {attempt+1}/10): {src}")
            time.sleep(0.25)
        except Exception as e:
            log_warn(f"[FILE] Move failed (attempt {attempt+1}/10): {e}")
            time.sleep(0.25)

    log_error(f"[FILE] FAILED to move file after retries: {src} → {dst}")


# ============================================================
# EXTENSION HELPERS
# ============================================================

def get_extension(path: Path) -> str:
    return path.suffix.lower()


def is_temp_file(path: Path, temp_exts):
    return get_extension(path) in temp_exts


# ============================================================
# SANITIZATION HELPERS
# ============================================================

def sanitize_filename(name: str) -> str:
    """
    Removes invalid Windows filename characters.
    """
    invalid = '<>:"/\\|?*'
    cleaned = "".join(c for c in name if c not in invalid)
    cleaned = cleaned.strip().rstrip(".")
    return cleaned or "unnamed"


# ============================================================
# SAFE OPEN (OneDrive‑Safe)
# ============================================================

def safe_open(path: Path, mode="rb", retries=5, delay=0.15):
    """
    Opens a file with retry logic to avoid OneDrive sync locks.
    """
    for _ in range(retries):
        try:
            return open(path, mode)
        except Exception:
            time.sleep(delay)
    raise FileNotFoundError(f"[FILE] Could not safely open file: {path}")