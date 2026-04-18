import sqlite3
import hashlib
import json
from pathlib import Path
from datetime import datetime

from PIL import Image, ExifTags
import cv2
import numpy as np

from vision_ocr import extract_text_google_vision

# ------------------------------------------------------------
# CONFIG PATH RESOLUTION & DATABASE CONNECTION
# ------------------------------------------------------------
def _get_ingestion_paths(config: dict):
    config = config or {}
    
    sys_root = Path(config.get("system_root", "C:/SmartInbox"))
    db_path = sys_root / "faces.db"
    
    sorted_root = Path(config.get("destinations", {}).get("sorted_root", "C:/SmartInbox/Photos"))
    thumb_root = sorted_root / "Thumbs"
    face_thumb_root = sorted_root / "FaceThumbs"
    
    thumb_root.mkdir(parents=True, exist_ok=True)
    face_thumb_root.mkdir(parents=True, exist_ok=True)
    
    return db_path, thumb_root, face_thumb_root

def _get_db_connection(db_path: Path):
    """Returns a highly concurrent SQLite connection."""
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;") 
    return conn

# ------------------------------------------------------------
# Orientation fix (EXIF)
# ------------------------------------------------------------
def fix_orientation(path: Path):
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return

        orientation_key = None
        for k, v in ExifTags.TAGS.items():
            if v == "Orientation":
                orientation_key = k
                break

        if not orientation_key or orientation_key not in exif:
            return

        orientation = exif[orientation_key]

        if orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 8:
            img = img.rotate(90, expand=True)
        else:
            return

        # Save corrected
        img.save(path, quality=95, exif=img.info.get("exif", b""))
    except Exception:
        pass

# ------------------------------------------------------------
# SHA256
# ------------------------------------------------------------
def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# ------------------------------------------------------------
# EXIF EXTRACTION
# ------------------------------------------------------------
def extract_exif(path: Path):
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return None, None, None, None

        date_taken = None
        gps_lat = None
        gps_lon = None
        camera_model = None

        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            if tag == "DateTimeOriginal":
                date_taken = value
            elif tag == "Model":
                camera_model = str(value).strip()
            elif tag == "GPSInfo":
                try:
                    gps_data = {}
                    for t in value:
                        sub_tag = ExifTags.GPSTAGS.get(t, t)
                        gps_data[sub_tag] = value[t]

                    if "GPSLatitude" in gps_data and "GPSLongitude" in gps_data:
                        lat_ref = gps_data.get("GPSLatitudeRef", "N")
                        lon_ref = gps_data.get("GPSLongitudeRef", "W")
                        
                        def convert_to_degrees(val):
                            d0 = val[0]
                            m0 = val[1]
                            s0 = val[2]
                            return float(d0) + (float(m0) / 60.0) + (float(s0) / 3600.0)

                        gps_lat = convert_to_degrees(gps_data["GPSLatitude"])
                        if lat_ref != "N":
                            gps_lat = -gps_lat

                        gps_lon = convert_to_degrees(gps_data["GPSLongitude"])
                        if lon_ref != "E":
                            gps_lon = -gps_lon

                except Exception:
                    pass

        return date_taken, gps_lat, gps_lon, camera_model
    except Exception:
        return None, None, None, None

# ------------------------------------------------------------
# THUMBNAIL
# ------------------------------------------------------------
def generate_thumbnail(path: Path, sha: str, thumb_root: Path):
    out_path = thumb_root / f"{sha}.jpg"
    if out_path.exists():
        return out_path
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((400, 400))
        img.save(out_path, "JPEG", quality=80)
        return out_path
    except Exception:
        return None

# ------------------------------------------------------------
# FACE DETECTION
# ------------------------------------------------------------
def detect_faces(path: Path):
    try:
        img_cv = cv2.imread(str(path))
        if img_cv is None:
            return 0, []

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        face_list = []
        for (x, y, w, h) in faces:
            face_list.append({"box": [int(x), int(y), int(w), int(h)]})

        return len(faces), face_list
    except Exception:
        return 0, []

def generate_face_thumbnail(path: Path, sha: str, face_data: list, face_thumb_root: Path):
    if not face_data:
        return None
        
    out_path = face_thumb_root / f"{sha}_face0.jpg"
    if out_path.exists():
        return out_path
        
    try:
        x, y, w, h = face_data[0]["box"]
        img = Image.open(path).convert("RGB")
        
        margin = int(w * 0.2)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(img.width, x + w + margin)
        y2 = min(img.height, y + h + margin)
        
        face_img = img.crop((x1, y1, x2, y2))
        face_img.thumbnail((150, 150))
        face_img.save(out_path, "JPEG", quality=80)
        return out_path
    except Exception:
        return None

# ------------------------------------------------------------
# INIT DB
# ------------------------------------------------------------
def _init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS photos (
            sha256 TEXT PRIMARY KEY,
            filename TEXT,
            original_path TEXT,
            thumb_path TEXT,
            face_thumb_path TEXT,
            face_count INTEGER,
            tags TEXT,
            tag_scores TEXT,
            face_data TEXT,
            date_taken TEXT,
            gps_lat REAL,
            gps_lon REAL,
            created_at TEXT,
            camera_model TEXT,
            ocr_text TEXT,
            category TEXT,
            doc_type TEXT,
            doc_issuer TEXT,
            is_document INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()

# ------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------
def ingest_photo(path: Path, config: dict = None):
    db_path, thumb_root, face_thumb_root = _get_ingestion_paths(config)
    
    # Fix orientation first
    fix_orientation(path)

    sha = compute_sha256(path)
    filename = path.name

    date_taken, gps_lat, gps_lon, camera_model = extract_exif(path)

    thumb_path = generate_thumbnail(path, sha, thumb_root)

    face_count, face_data = detect_faces(path)
    face_thumb_path = generate_face_thumbnail(path, sha, face_data, face_thumb_root)

    tags, tag_scores = [], {}
    
    conn = _get_db_connection(db_path)
    _init_db(conn)

    conn.execute(
        """
        INSERT OR REPLACE INTO photos (
            sha256, filename, original_path, thumb_path, face_thumb_path,
            face_count, tags, tag_scores, face_data, date_taken,
            gps_lat, gps_lon, created_at, camera_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sha,
            filename,
            str(path),
            str(thumb_path) if thumb_path else None,
            str(face_thumb_path) if face_thumb_path else None,
            face_count,
            json.dumps(tags),
            json.dumps(tag_scores),
            json.dumps(face_data),
            date_taken,
            gps_lat,
            gps_lon,
            datetime.now().isoformat(),
            camera_model,
        )
    )

    conn.commit()
    conn.close()