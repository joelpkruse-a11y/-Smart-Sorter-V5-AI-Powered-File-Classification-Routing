import os
import tempfile
from datetime import datetime
from flask import (
    Flask, request, render_template_string,
    redirect, url_for, send_from_directory, jsonify
)

# Import your new Render‑safe engine
from smart_sorter_v5 import process_file_for_web, load_config

app = Flask(__name__)

# Load config once at startup
config = load_config()

# Preview folder for thumbnails
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREVIEW_FOLDER = os.path.join(BASE_DIR, "upload_previews")
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

# Processed folder (from config)
PROCESSED_FOLDER = config["paths"]["processed"]

# In‑memory upload history (same as before)
uploads = []

# ---------------------------------------------------------
# HTML TEMPLATE (unchanged UI)
# ---------------------------------------------------------
HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smart Sorter V6 – Dashboard</title>
<style>
/* (YOUR ENTIRE CSS BLOCK REMAINS UNCHANGED)
   I am not repeating it here to keep this message readable.
   Paste your full CSS exactly as it was. */
</style>
</head>

<body>
<div class="sidebar">
    <div class="sidebar-header">
        <div class="sidebar-logo">SS</div>
        <div class="sidebar-title">
            <span>Smart Sorter</span>
            <span>V6 Dashboard</span>
        </div>
    </div>

    <div class="sidebar-nav">
        <div class="nav-section-label">Workspace</div>
        <div class="nav-item active" data-section="upload">
            <span class="icon">⬆️</span>
            <span>Upload & Status</span>
        </div>
        <div class="nav-item" data-section="processed">
            <span class="icon">📂</span>
            <span>Processed Files</span>
        </div>
        <div class="nav-item" data-section="logs">
            <span class="icon">📜</span>
            <span>Logs</span>
        </div>
    </div>

    <div class="sidebar-footer">
        <span>Render · Flask</span>
        <button class="toggle-btn" id="themeToggle">Toggle theme</button>
    </div>
</div>

<div class="main">
    <!-- Upload & Status -->
    <div class="section active" id="section-upload">
        <div class="section-header">
            <h2>Upload & Status</h2>
            <span class="subtitle">Send a file through Smart Sorter and watch it route.</span>
        </div>

        <div class="upload-box">
            <h3>Upload a File</h3>
            <p class="muted">Drag & drop a file below or click to browse.</p>
            <form id="uploadForm" method="post" enctype="multipart/form-data">
                <label class="drop-zone" id="dropZone">
                    <span id="dropText">Drop file here or click to select</span>
                    <input type="file" name="file" id="fileInput" required>
                </label>
                <button type="submit" class="upload-btn">Upload to Smart Sorter</button>
                <div class="progress-bar" id="progressBar"><div class="progress-inner"></div></div>
            </form>
        </div>

        <div class="table-card">
            <h3>Recent Uploads</h3>
            <table>
                <tr>
                    <th>Filename</th>
                    <th>Uploaded</th>
                    <th>Status</th>
                    <th>Category</th>
                    <th>Confidence</th>
                    <th>Summary</th>
                    <th>Preview</th>
                    <th>Download</th>
                </tr>

                {% for u in uploads %}
                <tr>
                    <td>{{ u.filename }}</td>
                    <td>{{ u.upload_time }}</td>

                    <td>
                        {% if u.status == 'Completed' %}
                            <span class="status-badge completed">Completed</span>
                        {% elif u.status == 'Processing' %}
                            <span class="status-badge processing">Processing</span>
                        {% else %}
                            <span class="status-badge failed">{{ u.status }}</span>
                        {% endif %}
                    </td>

                    <td><span class="category-tag">{{ u.category or 'Pending' }}</span></td>
                    <td>{{ '%.2f'|format(u.confidence) if u.confidence is not none else 'N/A' }}</td>
                    <td class="summary-cell">{{ u.summary or 'Processing...' }}</td>

                    <td>
                        {% if u.preview %}
                            <img src="{{ url_for('preview_file', filename=u.preview) }}" class="preview-img">
                        {% else %}
                            <span class="muted">No preview</span>
                        {% endif %}
                    </td>

                    <td>
                        {% if u.final_filename and u.status == 'Completed' %}
                            <a href="{{ url_for('download_processed', filename=u.final_filename) }}" class="download-btn">Download</a>
                        {% else %}
                            <span class="muted">Not available</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>

    <!-- Processed Files Explorer -->
    <div class="section" id="section-processed">
        <div class="section-header">
            <h2>Processed Files</h2>
            <span class="subtitle">Browse what Smart Sorter has routed into your processed folder.</span>
        </div>

        <div class="table-card">
            <h3>Files in /processed</h3>
            <div class="file-list">
                {% if processed_files %}
                    {% for f in processed_files %}
                    <div class="file-row">
                        <div>
                            <div>{{ f.name }}</div>
                            <div class="path">{{ f.rel_path }}</div>
                        </div>
                        <div>
                            <a href="{{ url_for('download_processed', filename=f.name) }}" class="download-btn">Download</a>
                            <form method="post" action="{{ url_for('delete_processed') }}" style="display:inline;">
                                <input type="hidden" name="filename" value="{{ f.name }}">
                                <input type="hidden" name="rel_path" value="{{ f.rel_path }}">
                                <button type="submit" class="delete-btn">Delete</button>
                            </form>
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <span class="muted">No processed files found yet.</span>
                {% endif %}
            </div>
        </div>
    </div>

    <!-- Logs -->
    <div class="section" id="section-logs">
        <div class="section-header">
            <h2>Logs</h2>
            <span class="subtitle">Recent Smart Sorter activity (best-effort view).</span>
        </div>

        <div class="logs-box" id="logsBox">
            Loading logs…
        </div>
    </div>
</div>

<script>
/* (YOUR FULL JS BLOCK REMAINS UNCHANGED)
   Paste your existing JS exactly as it was. */
</script>

</body>
</html>
"""

# ---------------------------------------------------------
# Helper: list processed files
# ---------------------------------------------------------
def list_processed_files():
    results = []
    for root, dirs, files in os.walk(PROCESSED_FOLDER):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, PROCESSED_FOLDER)
            results.append({"name": name, "rel_path": rel})
    return results

# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------
@app.route('/preview/<filename>')
def preview_file(filename):
    return send_from_directory(PREVIEW_FOLDER, filename)

@app.route('/download/<path:filename>')
def download_processed(filename):
    for root, dirs, files in os.walk(PROCESSED_FOLDER):
        if filename in files:
            return send_from_directory(root, filename, as_attachment=True)
    return "File not found", 404

@app.route('/delete_processed', methods=['POST'])
def delete_processed():
    filename = request.form.get('filename')
    rel_path = request.form.get('rel_path', '')
    if not filename:
        return redirect(url_for('upload_file'))

    target = os.path.join(PROCESSED_FOLDER, rel_path)
    if os.path.isfile(target):
        try:
            os.remove(target)
        except Exception:
            pass

    return redirect(url_for('upload_file', view='processed'))

@app.route('/logs')
def get_logs():
    log_path = config["paths"].get("logs")
    if not log_path or not os.path.isfile(log_path):
        return jsonify({"logs": "No log file found."})

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[-8000:]
        return jsonify({"logs": content})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {e}"})


# ---------------------------------------------------------
# MAIN UPLOAD ROUTE (Render‑safe)
# ---------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part', 400

        file = request.files['file']
        if file.filename == '':
            return 'No selected file', 400

        # Save preview
        preview_path = os.path.join(PREVIEW_FOLDER, file.filename)
        file.save(preview_path)

        # Save temp copy for processing
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.stream.seek(0)
            file.save(tmp.name)
            tmp_path = tmp.name

        # Create upload record
        record = {
            "filename": file.filename,
            "upload_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status": "Processing",
            "category": None,
            "confidence": None,
            "summary": None,
            "preview": file.filename,
            "final_filename": None,
        }
        uploads.append(record)

        # PROCESS SYNCHRONOUSLY (Render‑safe)
        result = process_file_for_web(tmp_path, config)

        record["status"] = result.get("status", "Failed")
        record["category"] = result.get("category")
        record["confidence"] = result.get("confidence")
        record["summary"] = result.get("summary")
        record["final_filename"] = result.get("final_filename")

        return redirect(url_for('upload_file'))

    # GET
    processed_files = list_processed_files()
    return render_template_string(
        HTML_TEMPLATE,
        uploads=uploads,
        processed_files=processed_files,
    )

# ---------------------------------------------------------
# ENTRY POINT (Render uses PORT env)
# ---------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)




