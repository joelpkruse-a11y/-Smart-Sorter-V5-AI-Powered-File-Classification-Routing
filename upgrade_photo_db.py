import sqlite3
from pathlib import Path

DB_PATH = Path("C:/SmartInbox/faces.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Add created_at column if missing
try:
    cur.execute("ALTER TABLE photos ADD COLUMN created_at TEXT")
    print("Added created_at column.")
except Exception as e:
    print("created_at column already exists or cannot be added:", e)

# Add camera_model column if missing
try:
    cur.execute("ALTER TABLE photos ADD COLUMN camera_model TEXT")
    print("Added camera_model column.")
except Exception as e:
    print("camera_model column already exists or cannot be added:", e)

conn.commit()
conn.close()