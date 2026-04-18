# ============================================================
# photo_duplicates.py — Smart Sorter V5.3
# Perceptual Hash Duplicate Detection (pHash)
# ============================================================

import json
import time
from pathlib import Path
from typing import Tuple, Optional

from PIL import Image
import imagehash

from utils.logging_utils import log_info, log_warn, log_error, log_diag
from utils.file_utils import safe_open

# ============================================================
# DATABASE PATH (required by photo_dashboard.py)
# ============================================================
DB_PATH = Path("C:/SmartInbox/faces.db")


# ============================================================
# INDEX FILE (persistent)
# ============================================================

INDEX_PATH = Path("C:/SmartInbox/photo_index.json")


def _load_index() -> dict:
    """Loads the persistent photo hash index."""
    if not INDEX_PATH.exists():
        return {}

    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_warn(f"[DUP] Failed to load index: {e}")
        return {}


def _save_index(index: dict):
    """Saves the persistent photo hash index."""
    try:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except Exception as e:
        log_error(f"[DUP] Failed to save index: {e}")


# ============================================================
# HASHING
# ============================================================

def _compute_phash(path: Path) -> Optional[str]:
    """Computes perceptual hash (pHash) for an image."""
    try:
        with safe_open(path, "rb") as f:
            img = Image.open(f)
            img = img.convert("RGB")
            ph = str(imagehash.phash(img))
            log_diag(f"[DUP] pHash for {path.name}: {ph}")
            return ph
    except Exception as e:
        log_warn(f"[DUP] Failed to compute pHash for {path.name}: {e}")
        return None


# ============================================================
# DUPLICATE CHECK
# ============================================================

def is_photo_duplicate(path: Path) -> Tuple[bool, str]:
    """
    Returns:
        (True, method) if duplicate
        (False, "") if unique

    method = "phash" or "filename" or "unknown"
    """
    index = _load_index()

    # --------------------------------------------------------
    # 1) Filename-based quick check
    # --------------------------------------------------------
    name = path.name.lower()
    if name in index.get("filenames", {}):
        log_info(f"[DUP] Duplicate detected by filename: {name}")
        return True, "filename"

    # --------------------------------------------------------
    # 2) pHash-based check
    # --------------------------------------------------------
    ph = _compute_phash(path)
    if not ph:
        return False, ""

    if ph in index.get("phashes", {}):
        log_info(f"[DUP] Duplicate detected by pHash: {path.name}")
        return True, "phash"

    # --------------------------------------------------------
    # 3) Not a duplicate → add to index
    # --------------------------------------------------------
    index.setdefault("filenames", {})[name] = True
    index.setdefault("phashes", {})[ph] = True
    _save_index(index)

    log_diag(f"[DUP] New unique photo indexed: {path.name}")
    return False, ""

# ============================================================
# FACE SIMILARITY SUPPORT (required by photo_dashboard.py)
# ============================================================

import sqlite3

def _load_face_db():
    """Load all face entries from the faces table."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT sha256, face_hash FROM faces")
        rows = cur.fetchall()
    except Exception:
        rows = []
    conn.close()
    return rows


def _compute_face_hash_for_similarity(image_path: str):
    """Compute a perceptual hash for face similarity."""
    try:
        img = Image.open(image_path).convert("L").resize((64, 64))
        return str(imagehash.phash(img))
    except Exception:
        return None


def find_similar_faces(image_path: str, threshold: int = 10):
    """
    Compute similarity between the given image and all stored face hashes.
    Returns a list of (sha256, distance).
    """
    target_hash = _compute_face_hash_for_similarity(image_path)
    if not target_hash:
        return []

    target_hash_obj = imagehash.hex_to_hash(target_hash)
    results = []

    for row in _load_face_db():
        db_hash = row["face_hash"]
        if not db_hash:
            continue

        try:
            db_hash_obj = imagehash.hex_to_hash(db_hash)
            distance = target_hash_obj - db_hash_obj
        except Exception:
            continue

        if distance <= threshold:
            results.append((row["sha256"], distance))

    return sorted(results, key=lambda x: x[1])


def cluster_faces(threshold: int = 10):
    """
    Group faces into clusters based on perceptual hash distance.
    Returns a list of clusters, each cluster is a list of sha256 strings.
    """
    rows = _load_face_db()
    clusters = []

    for row in rows:
        sha = row["sha256"]
        face_hash = row["face_hash"]
        if not face_hash:
            continue

        try:
            hash_obj = imagehash.hex_to_hash(face_hash)
        except Exception:
            continue

        placed = False
        for cluster in clusters:
            first_sha = cluster[0]
            first_hash = next((r["face_hash"] for r in rows if r["sha256"] == first_sha), None)
            if not first_hash:
                continue

            try:
                first_hash_obj = imagehash.hex_to_hash(first_hash)
                if (hash_obj - first_hash_obj) <= threshold:
                    cluster.append(sha)
                    placed = True
                    break
            except Exception:
                continue

        if not placed:
            clusters.append([sha])

    return clusters