# ============================================================
# logging_utils.py — Smart Sorter V5.3
# Centralized Logging (Console + File + Color Output)
# ============================================================

import sys
import logging
from datetime import datetime
from pathlib import Path

# ============================================================
# COLOR MAP (Console Only)
# ============================================================

COLOR_MAP = {
    "success": "\033[92m",
    "error":   "\033[91m",
    "warn":    "\033[93m",
    "diag":    "\033[96m",
    "info":    "\033[97m",
    "reset":   "\033[0m",
}

# ============================================================
# LOGGER SETUP (File Logging)
# ============================================================

logger = logging.getLogger("smart_sorter")
logger.setLevel(logging.DEBUG)

# Prevent duplicate handlers if imported multiple times
if not logger.handlers:
    log_dir = Path("C:/SmartInbox/System")
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(
        log_dir / "sorter.log",
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    logger.addHandler(file_handler)

# ============================================================
# INTERNAL CONSOLE PRINTER
# ============================================================

def _console_print(level: str, msg: str):
    """Prints color-coded console output."""
    color = COLOR_MAP.get(level, COLOR_MAP["info"])
    reset = COLOR_MAP["reset"]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{color}[{level.upper()}] {ts} {msg}{reset}")

# ============================================================
# PUBLIC LOGGING FUNCTIONS
# ============================================================

def log_info(msg: str):
    logger.info(msg)
    _console_print("info", msg)

def log_warn(msg: str):
    logger.warning(msg)
    _console_print("warn", msg)

def log_error(msg: str):
    logger.error(msg)
    _console_print("error", msg)

def log_diag(msg: str):
    logger.debug(msg)
    _console_print("diag", msg)

def log_success(msg: str):
    logger.info(msg)
    _console_print("success", msg)

# ============================================================
# COMPATIBILITY WRAPPER (legacy `log()` calls)
# ============================================================

def log(msg: str, level: str = "info"):
    """
    Backwards-compatible wrapper for legacy calls like:
        log("message")
        log("message", "warn")
        log("message", "error")
    """
    level = level.lower()

    if level in ("info", "i"):
        return log_info(msg)
    if level in ("warn", "warning", "w"):
        return log_warn(msg)
    if level in ("error", "err", "e"):
        return log_error(msg)
    if level in ("diag", "debug", "d"):
        return log_diag(msg)
    if level in ("success", "ok"):
        return log_success(msg)

    # Fallback
    return log_info(msg)