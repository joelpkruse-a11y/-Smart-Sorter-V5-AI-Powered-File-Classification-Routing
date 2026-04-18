import os
import re
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS

# ---------------------------------------------------------
# SANITIZATION
# ---------------------------------------------------------
def sanitize_filename(name: str) -> str:
    name = name.replace(":", "-").replace("/", "-").replace("\\", "-")
    name = name.replace("*", "-").replace("?", "").replace("\"", "")
    name = name.replace("<", "").replace(">", "").replace("|", "")
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    return name

def safe_join(folder: str, filename: str) -> str:
    filename = sanitize_filename(filename)
    return os.path.join(folder, filename)

# ---------------------------------------------------------
# EXTRACT DATE FROM METADATA (Option C)
# ---------------------------------------------------------
def extract_date_from_metadata(metadata: dict):
    if not metadata:
        return None

    for key in ["date", "statement_date", "service_date", "created", "modified"]:
        if key in metadata:
            try:
                return datetime.fromisoformat(metadata[key])
            except Exception:
                pass

    return None

# ---------------------------------------------------------
# EXTRACT DATE FROM EXIF (Option C priority #1)
# ---------------------------------------------------------
def extract_exif_date(path: str):
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return None

        for tag, value in exif.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "DateTimeOriginal":
                try:
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                except:
                    pass
    except:
        pass

    return None

# ---------------------------------------------------------
# BUILD FINAL FILENAME (your rules)
# ---------------------------------------------------------
def generate_final_filename(result: dict, original_path: str, log):
    category = (result.get("category", "other") or "other").lower()
    metadata = result.get("metadata", {}) or {}
    raw_name = result.get("filename", "") or ""

    base_name, _ = os.path.splitext(raw_name)
    ext = os.path.splitext(original_path)[1].lower()

    # ---------------------------------------------------------
    # RULESET
    # ---------------------------------------------------------

    # 1. PHOTOS → include date, no category
    if category == "photos":
        # Priority 1: EXIF
        date_obj = extract_exif_date(original_path)

        # Priority 2: metadata
        if not date_obj:
            date_obj = extract_date_from_metadata(metadata)

        # Priority 3: filesystem
        if not date_obj:
            try:
                ts = os.path.getmtime(original_path)
                date_obj = datetime.fromtimestamp(ts)
            except:
                date_obj = datetime.now()

        date_str = date_obj.strftime("%Y-%m-%d")
        final_name = f"{date_str} {base_name}{ext}"

    # 2. VIDEOS → no date, no category
    elif category == "videos":
        final_name = base_name + ext

    # 3. OTHER → no date, no category
    elif category == "other":
        final_name = base_name + ext

    # 4. MEANINGFUL CATEGORIES → category prefix
    else:
        final_name = f"{category.capitalize()} - {base_name}{ext}"

    final_name = sanitize_filename(final_name)
    log(f"[NAME-V3] Final filename (clean rules): {final_name}", "diag")
    return final_name

# ---------------------------------------------------------
# ROUTING (dynamic folders under sorted_root) — V5.4 Upgrade
# ---------------------------------------------------------
def route_file(category: str,
               final_filename: str,
               config: dict,
               log,
               created_date=None,
               subcategory=None):

    import os
    from pathlib import Path

    destinations = config.get("destinations", {}) or {}
    category = (category or "other").strip().lower()

    # Helper: safe join → returns Path
    def _safe_join(folder, filename):
        folder = folder or "."
        return Path(folder) / filename

    # Helper: ensure folder exists
    def _ensure(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            log(f"[ROUTER] ERROR creating folder '{folder}': {e}", "error")
        return folder

    # Helper: collision-safe filename → returns Path
    def _resolve_collision(folder, filename):
        base = Path(folder) / filename
        if not base.exists():
            return base

        stem = base.stem
        ext = base.suffix or ".pdf"
        counter = 1

        new_path = Path(folder) / f"{stem}__{counter}{ext}"
        while new_path.exists():
            counter += 1
            new_path = Path(folder) / f"{stem}__{counter}{ext}"

        log(f"[ROUTER] Filename collision resolved → {new_path.name}", "diag")
        return new_path

    # ---------------------------------------------------------
    # PHOTOS → date-based routing
    # ---------------------------------------------------------
    if category == "photos":
        photos_root = destinations.get("photos", "")
        if not photos_root:
            log("[ROUTER] No 'photos' destination configured.", "warn")
            return _safe_join(destinations.get("other", ""), final_filename)

        if created_date:
            year = created_date.strftime("%Y")
            month = created_date.strftime("%m")
            folder = os.path.join(photos_root, year, month)
        else:
            folder = photos_root

        folder = _ensure(folder)
        return _resolve_collision(folder, final_filename)

    # ---------------------------------------------------------
    # VIDEOS → date-based routing
    # ---------------------------------------------------------
    if category == "videos":
        videos_root = destinations.get("videos", "")
        if not videos_root:
            log("[ROUTER] No 'videos' destination configured.", "warn")
            return _safe_join(destinations.get("other", ""), final_filename)

        if created_date:
            year = created_date.strftime("%Y")
            month = created_date.strftime("%m")
            folder = os.path.join(videos_root, year, month)
        else:
            folder = videos_root

        folder = _ensure(folder)
        return _resolve_collision(folder, final_filename)

    # ---------------------------------------------------------
    # PREDEFINED CATEGORIES (match config.json)
    # ---------------------------------------------------------
    if category in destinations:
        folder = _ensure(destinations[category])
        return _resolve_collision(folder, final_filename)

    # ---------------------------------------------------------
    # DYNAMIC CATEGORIES → create new top-level folder
    # ---------------------------------------------------------
    sorted_root = destinations.get("sorted_root", "")
    if not sorted_root:
        log("[ROUTER] No 'sorted_root' configured.", "error")
        return _safe_join(".", final_filename)

    dynamic_folder = os.path.join(sorted_root, category.capitalize())
    dynamic_folder = _ensure(dynamic_folder)

    return _resolve_collision(dynamic_folder, final_filename)
