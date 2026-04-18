# ============================================================
# smart_sorter_cloud.py — Render Deployment Entry Point
# ============================================================

import os
from pathlib import Path
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

# Import your existing pipeline logic and loggers!
from smart_sorter_v5 import process_file
from utils.logging_utils import log_info, log_warn, log_error

app = Flask(__name__)

# Render uses ephemeral storage in /tmp for temporary uploads
UPLOAD_FOLDER = Path("/tmp/SmartInbox/Incoming")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Prevent abuse: Limit uploads to 50MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 

# ------------------------------------------------------------
# HEALTH ENDPOINT (Required by Render to know your app is alive)
# ------------------------------------------------------------
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Smart Sorter API is running."}), 200

# ------------------------------------------------------------
# MAIN UPLOAD ENDPOINT
# ------------------------------------------------------------
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        log_warn("[API] Upload rejected: No file part in request.")
        return jsonify({"error": "No file part in the request"}), 400
        
    file = request.files['file']
    
    if file.filename == '':
        log_warn("[API] Upload rejected: Empty filename.")
        return jsonify({"error": "No selected file"}), 400
        
    if file:
        # Secure the filename to prevent directory traversal attacks
        filename = secure_filename(file.filename)
        save_path = UPLOAD_FOLDER / filename
        
        # 1. Save the file temporarily to the Render instance
        log_info(f"[API] Receiving file: {filename}")
        file.save(save_path)
        
        # 2. Pass it directly to your existing V5 pipeline
        try:
            process_file(save_path)
            log_info(f"[API] Pipeline processing complete for {filename}")
            
            return jsonify({
                "status": "success", 
                "message": f"{filename} sorted successfully."
            }), 200
            
        except Exception as e:
            log_error(f"[API] Pipeline failed for {filename}: {e}")
            return jsonify({
                "status": "error", 
                "message": f"Pipeline failed: {str(e)}"
            }), 500

# ============================================================
# START THE SERVER (Local Debugging Only)
# Note: Render uses Gunicorn to run this in production, 
# so this block only fires if you run the file manually.
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    log_info(f"[STARTUP] Starting Cloud Smart Sorter on port {port}...")
    app.run(host='0.0.0.0', port=port)