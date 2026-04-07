🛠 Smart Sorter V5 — Troubleshooting Guide
This guide helps diagnose and fix the most common issues you may encounter while running Smart Sorter V5.
Each issue includes symptoms, causes, and step‑by‑step fixes.

⚡ 1. Files Aren’t Moving
Symptoms
File stays in the incoming folder

No log entry

No dashboard event

No error message

Likely Causes
OneDrive still writing the file

File is locked by another process

File extension is in temp_extensions

File watcher didn’t detect the event

Fix
Wait 5–10 seconds — OneDrive may still be syncing.

Check the log:

Code
C:/SmartInbox/System/sorter.log
Ensure the file extension is not in:

json
"temp_extensions": [".tmp", ".crdownload", ...]
Restart Smart Sorter:

Code
Ctrl + C
python smart_sorter_v5.py
⚡ 2. Files Are Misclassified
Symptoms
A document goes into the wrong category

A photo is treated as a document

A document is treated as a photo

Likely Causes
Gemini misinterpreted the content

OCR extracted noisy text

Smart Mode V2 refinement rules triggered

Document‑photo heuristics detected text in an image

Fix
Open the dashboard:

Code
http://localhost:8765
Review:

Gemini category

Smart Mode category

Reasoning

Extracted text

If the category is consistently wrong:

Add a new predefined category to config.json

Or adjust Smart Mode V2 rules (if needed)

⚡ 3. Photos Are Missing Dates or Have Wrong Dates
Symptoms
Photo filename missing date prefix

Wrong date (e.g., 1970 or today’s date)

Photos routed to wrong year/month

Likely Causes
Missing EXIF metadata

Corrupted EXIF date

Screenshot (no EXIF)

Metadata didn’t include a date

Fix
Smart Sorter uses Option C:

EXIF date

Metadata date

Filesystem timestamp

If EXIF is missing or wrong:

The fallback is filesystem timestamp

This is expected behavior

To fix EXIF:

Use a tool like ExifTool to repair the date

Or manually rename the file before sorting

⚡ 4. Videos Not Routing Correctly
Symptoms
Videos appear in the wrong folder

Videos get categorized as “other”

Videos don’t get date‑based routing

Likely Causes
Video extension missing from:

json
"video_extensions": [...]
File is corrupted

File is locked by OneDrive

Fix
Add missing extensions:

json
".mp4", ".mov", ".avi", ".mkv", ".lrv", ".insv"
Restart Smart Sorter

Re‑drop the file

⚡ 5. Dashboard Not Loading
Symptoms
Browser shows “connection refused”

Dashboard never loads

Port 8765 already in use

Likely Causes
Dashboard process crashed

Another app is using port 8765

Firewall blocking local port

Fix
Restart Smart Sorter

Try a different browser

Change dashboard port in:

python
start_dashboard(port=8765)
Ensure no VPN/firewall is blocking localhost

⚡ 6. “Permission Denied” or “File Locked” Errors
Symptoms
Log shows:

Code
WinError 32
PermissionError
File doesn’t move

Likely Causes
OneDrive syncing

File open in another app

Antivirus scanning

Fix
Smart Sorter already retries 8 times.
If still failing:

Close any app that may have the file open

Pause OneDrive sync temporarily

Move the file manually

Restart Smart Sorter

⚡ 7. New Categories Not Being Created
Symptoms
Unknown categories go to “Other”

Dynamic folders not appearing

Likely Causes
sorted_root missing from config

Category name matches an existing key

Router not updated

Fix
Ensure this exists in config.json:

json
"sorted_root": "C:/Users/joelk/OneDrive/Smart Inbox/Incoming/Sorted"
And your router uses:

python
sorted_root = destinations.get("sorted_root")
⚡ 8. Smart Sorter Crashes on Startup
Symptoms
Python error on launch

Missing module error

Config load error

Likely Causes
Invalid JSON syntax

Missing dependency

Wrong Python version

Fix
Validate config.json using:
https://jsonlint.com

Reinstall dependencies:

Code
pip install pymupdf python-docx pillow numpy
Ensure Python 3.10+

Check log for details

⚡ 9. OCR Not Working
Symptoms
Document photos not detected

Extracted text is empty

Gemini misclassifies image documents

Likely Causes
Google Vision disabled

Missing Vision API credentials

OpenCV not installed

Fix
Ensure:

json
"use_google_vision": true
Set environment variable:

Code
GOOGLE_APPLICATION_CREDENTIALS="C:/path/to/key.json"
Install OpenCV:

Code
pip install opencv-python
⚡ 10. Gemini Not Responding
Symptoms
No Gemini output

Fallback classifier always used

Log shows Gemini errors

Likely Causes
Invalid API key

Network issue

Gemini disabled in config

Fix
Verify:

json
"enabled": true
Check API key

Restart Smart Sorter

Check logs for:

Code
[AI] Gemini call crashed
🧹 Resetting Smart Sorter (Last Resort)
If everything seems broken:

Stop Smart Sorter

Delete:

Code
C:/SmartInbox/System/sorter.log
Restart Smart Sorter

Re‑drop a test file

This forces a clean state.
