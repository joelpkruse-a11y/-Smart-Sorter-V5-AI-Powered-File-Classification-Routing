import os
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ============================================================
# OneDrive-Safe File Readiness Check
# ============================================================
def wait_for_file_ready(path, timeout=20, log=print):
    """
    Ensures the file is:
    - Present
    - Not a OneDrive temp/partial file
    - Size-stable
    - Not locked
    """
    last_size = -1
    stable_count = 0

    for _ in range(timeout * 10):
        if not os.path.exists(path):
            time.sleep(0.1)
            continue

        # Skip OneDrive temp files
        lower = path.lower()
        if lower.endswith((".tmp", ".partial", ".download", ".lnk", ".ini")):
            time.sleep(0.1)
            continue

        try:
            size = os.path.getsize(path)
        except OSError:
            time.sleep(0.1)
            continue

        # Check lock
        try:
            with open(path, "rb"):
                pass
        except Exception:
            time.sleep(0.1)
            continue

        # Check size stability
        if size == last_size:
            stable_count += 1
            if stable_count >= 5:  # 0.5 seconds stable
                return True
        else:
            stable_count = 0

        last_size = size
        time.sleep(0.1)

    log(f"[READY] Timeout waiting for file to stabilize: {path}", "warn")
    return False


# ============================================================
# Watchdog Event Handler (OneDrive-Safe)
# ============================================================
class OneDriveSafeHandler(FileSystemEventHandler):
    def __init__(self, folder_name, folder_path, callback, log):
        super().__init__()
        self.folder_name = folder_name
        self.folder_path = folder_path
        self.callback = callback
        self.log = log

    def on_created(self, event):
        if event.is_directory:
            return

        path = os.path.normpath(event.src_path)

        # Skip temp/partial files
        if path.lower().endswith((".tmp", ".partial", ".download", ".lnk", ".ini")):
            return

        self.log(f"[DIAG] Detected new file: {path}", "diag")

        # Wait for OneDrive-safe readiness
        if not wait_for_file_ready(path, timeout=20, log=self.log):
            self.log(f"[WARN] File never stabilized: {path}", "warn")
            return

        # Hand off to Smart Sorter worker
        self.callback(path)


# ============================================================
# Watcher Loop
# ============================================================
def start_onedrive_safe_watchers(watch_folders: dict, callback, log):
    observers = []

    for name, folder_entry in watch_folders.items():

        # Normalize: allow string OR list
        if isinstance(folder_entry, str):
            folder_list = [folder_entry]
        elif isinstance(folder_entry, list):
            folder_list = folder_entry
        else:
            log(f"[WARN] Invalid folder entry for {name}: {folder_entry}", "warn")
            continue

        # Process each folder in the list
        for folder in folder_list:
            folder = os.path.normpath(folder)

            if not os.path.isdir(folder):
                log(f"[WARN] Watch folder does not exist: {folder}", "warn")
                continue

            log(f"[INFO] Watching: [{name}] {folder}", "info")

            handler = OneDriveSafeHandler(name, folder, callback, log)
            observer = Observer()
            observer.schedule(handler, folder, recursive=False)
            observer.start()
            observers.append(observer)

    # Keep thread alive
    def loop():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            for obs in observers:
                obs.stop()
            for obs in observers:
                obs.join()

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    return observers
