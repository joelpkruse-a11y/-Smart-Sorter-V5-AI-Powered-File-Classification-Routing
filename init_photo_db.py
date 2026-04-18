import sqlite3
from pathlib import Path

DB_PATH = Path("C:/SmartInbox/faces.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Main photo table
cur.execute("""
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
    gps_lon REAL
)
""")

# Face similarity table
cur.execute("""
CREATE TABLE IF NOT EXISTS faces (
    sha256 TEXT PRIMARY KEY,
    face_hash TEXT
)
""")

conn.commit()
conn.close()

print("Photo dashboard database initialized.")