import os
import tempfile
import threading
from datetime import datetime

from flask import (
    Flask,
    request,
    render_template_string,
    redirect,
    url_for,
    send_from_directory,
    jsonify,
)

# V6 pipeline + config
from smart_sorter_v6 import classify_and_route_v6, load_config_v6

app = Flask(__name__)

# Load Smart Sorter V6 config once (Render-friendly: allow override via env)
CONFIG_PATH = os.getenv("SMART_SORTER_CONFIG", "config.json")
config = load_config_v6(CONFIG_PATH)

# Folders from config
INCOMING_FOLDER = config["paths"]["incoming"]
PROCESSED_FOLDER = config["paths"]["processed"]

# Optional logs path (best-effort)
LOG_FILE = config["paths"].get(
    "logs",
    os.path.join(os.path.dirname(__file__), "smart_sorter.log")
)

# Ensure preview folder exists (for UI thumbnails)
PREVIEW_FOLDER = os.path.join(os.path.dirname(__file__), "upload_previews")
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

# In-memory upload records (demo only)
uploads = []

# ---------------------------
# HTML TEMPLATE (unchanged UI)
# ---------------------------
HTML_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smart Sorter V6 – Dashboard</title>

<style>
:root {
    --bg-main: #0b1120;
    --bg-elevated: rgba(15, 23, 42, 0.85);
    --bg-glass: rgba(15, 23, 42, 0.65);
    --border-subtle: rgba(148, 163, 184, 0.35);
    --accent: #4f46e5;
    --accent-soft: rgba(79, 70, 229, 0.12);
    --accent-strong: #22c55e;
    --text-main: #e5e7eb;
    --text-muted: #9ca3af;
    --danger: #ef4444;
    --danger-soft: rgba(239, 68, 68, 0.12);
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 0;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: radial-gradient(circle at top, #1f2937 0, #020617 55%, #000 100%);
    color: var(--text-main);
    display: flex;
    min-height: 100vh;
}

/* Sidebar */

.sidebar {
    width: 260px;
    padding: 18px 18px 24px 18px;
    background: var(--bg-glass);
    border-right: 1px solid var(--border-subtle);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    display: flex;
    flex-direction: column;
    position: sticky;
    top: 0;
    height: 100vh;
}

.sidebar-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 18px;
}

.sidebar-logo {
    width: 32px;
    height: 32px;
    border-radius: 12px;
    background: radial-gradient(circle at 30% 20%, #22c55e, #4f46e5);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 1.1rem;
    color: #f9fafb;
}

.sidebar-title {
    display: flex;
    flex-direction: column;
}

.sidebar-title span:first-child {
    font-size: 0.9rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.sidebar-title span:last-child {
    font-size: 1.05rem;
    font-weight: 600;
}

.sidebar-nav {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.nav-section-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-muted);
    margin: 12px 4px 4px 4px;
}

.nav-item {
    border-radius: 999px;
    padding: 7px 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 0.85rem;
    color: var(--text-muted);
    border: 1px solid transparent;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.nav-item span.icon {
    font-size: 1rem;
}

.nav-item.active {
    background: var(--accent-soft);
    color: #e5e7eb;
    border-color: rgba(79, 70, 229, 0.6);
}

.nav-item:hover:not(.active) {
    background: rgba(15, 23, 42, 0.9);
    border-color: rgba(148, 163, 184, 0.4);
    color: #e5e7eb;
}

.sidebar-footer {
    margin-top: auto;
    font-size: 0.75rem;
    color: var(--text-muted);
    border-top: 1px solid rgba(15, 23, 42, 0.9);
    padding-top: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.toggle-btn {
    padding: 5px 10px;
    border-radius: 999px;
    border: 1px solid var(--border-subtle);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.75rem;
}

/* Main content */

.main {
    flex: 1;
    padding: 18px 24px 32px 24px;
    overflow-y: auto;
}

/* Cards / sections */

.section {
    display: none;
}

.section.active {
    display: block;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 12px;
}

.section-header h2 {
    margin: 0;
    font-size: 1.2rem;
}

.section-header .subtitle {
    font-size: 0.85rem;
    color: var(--text-muted);
}

/* Upload card */

.upload-box {
    max-width: 720px;
    padding: 22px 22px 20px 22px;
    background: var(--bg-elevated);
    border-radius: 18px;
    border: 1px solid var(--border-subtle);
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.7);
}

.upload-box h3 {
    margin: 0 0 4px 0;
    font-size: 1.05rem;
}

.muted {
    color: var(--text-muted);
    font-size: 0.85rem;
}

.drop-zone {
    margin-top: 16px;
    border: 1px dashed rgba(148, 163, 184, 0.8);
    border-radius: 14px;
    padding: 26px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s ease, background 0.2s ease;
    background: rgba(15, 23, 42, 0.7);
}

.drop-zone.dragover {
    border-color: var(--accent);
    background: rgba(79, 70, 229, 0.12);
}

.drop-zone input[type="file"] {
    display: none;
}

.upload-btn {
    margin-top: 16px;
    padding: 9px 18px;
    border-radius: 999px;
    border: none;
    background: var(--accent);
    color: #f9fafb;
    font-weight: 500;
    cursor: pointer;
    font-size: 0.9rem;
}

.upload-btn:hover {
    background: #4338ca;
}

.progress-bar {
    margin-top: 12px;
    width: 100%;
    height: 6px;
    border-radius: 999px;
    background: rgba(30, 64, 175, 0.4);
    overflow: hidden;
    display: none;
}

.progress-inner {
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, #4f46e5, #22c55e);
    animation: progress-pulse 1.2s infinite ease-in-out;
}

@keyframes progress-pulse {
    0% { transform: translateX(-100%); }
    50% { transform: translateX(0%); }
    100% { transform: translateX(100%); }
}

/* Table */

.table-card {
    margin-top: 22px;
    padding: 18px 18px 14px 18px;
    background: var(--bg-elevated);
    border-radius: 18px;
    border: 1px solid var(--border-subtle);
}

.table-card h3 {
    margin: 0 0 10px 0;
    font-size: 1rem;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}

th, td {
    padding: 7px 8px;
    border-bottom: 1px solid rgba(31, 41, 55, 0.9);
    text-align: left;
    vertical-align: top;
}

th {
    font-weight: 600;
    color: var(--text-muted);
    font-size: 0.8rem;
}

.status-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 500;
}

.status-badge.completed {
    background: rgba(22, 163, 74, 0.18);
    color: #4ade80;
}

.status-badge.processing {
    background: rgba(59, 130, 246, 0.18);
    color: #93c5fd;
}

.status-badge.failed {
    background: var(--danger-soft);
    color: #fecaca;
}

.category-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(129, 140, 248, 0.18);
    color: #c7d2fe;
    font-size: 0.75rem;
}

.summary-cell {
    max-width: 260px;
    white-space: normal;
}

.preview-img {
    max-width: 70px;
    max-height: 70px;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid rgba(31, 41, 55, 0.9);
}

/* Download / delete buttons */

.download-btn,
.delete-btn {
    padding: 5px 10px;
    border-radius: 999px;
    font-size: 0.8rem;
    text-decoration: none;
    border: 1px solid transparent;
    cursor: pointer;
}

.download-btn {
    background: #4a90e2;
    color: white;
}

.download-btn:hover {
    background: #357ab8;
}

.delete-btn {
    background: transparent;
    color: #fca5a5;
    border-color: rgba(248, 113, 113, 0.5);
}

.delete-btn:hover {
    background: var(--danger-soft);
}

/* Processed explorer */

.file-list {
    margin-top: 10px;
    font-size: 0.85rem;
}

.file-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px solid rgba(31, 41, 55, 0.9);
}

.file-row span.path {
    color: var(--text-muted);
    font-size: 0.8rem;
}

/* Logs */

.logs-box {
    padding: 16px;
    background: var(--bg-elevated);
    border-radius: 18px;
    border: 1px solid var(--border-subtle);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 0.8rem;
    max-height: 420px;
    overflow-y: auto;
    white-space: pre-wrap;
}

/* Responsive-ish */

@media (max-width: 900px) {
    .sidebar {
        display: none;
    }
    body {
        display: block;
    }
    .main {
        padding: 16px;
    }
}
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
                        {% if u.processed_filename and u.status == 'Completed' %}
                            <a href="{{ url_for('download_processed', filename=u.processed_filename) }}" class="download-btn">Download</a>
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
const body = document.body;
const themeToggle = document.getElementById('themeToggle');
themeToggle.addEventListener('click', () => {
    body.classList.toggle('dark-mode');
});

/* Sidebar navigation */
const navItems = document.querySelectorAll('.nav-item');
const sections = {
    upload: document.getElementById('section-upload'),
    processed: document.getElementById('section-processed'),
    logs: document.getElementById('section-logs'),
};

navItems.forEach(item => {
    item.addEventListener('click', () => {
        navItems.forEach(i => i.classList.remove('active'));
        item.classList.add('active');

        const target = item.getAttribute('data-section');
        Object.keys(sections).forEach(key => {
            sections[key].classList.toggle('active', key === target);
        });

        if (target === 'logs') {
            fetchLogs();
        }
    });
});

/* Upload interactions */
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const dropText = document.getElementById('dropText');
const progressBar = document.getElementById('progressBar');
const uploadForm = document.getElementById('uploadForm');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('dragover');
    dropText.textContent = 'Release to upload';
});
dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
    dropText.textContent = 'Drop file here or click to select';
});
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        dropText.textContent = e.dataTransfer.files[0].name;
    }
});
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        dropText.textContent = fileInput.files[0].name;
    }
});
uploadForm.addEventListener('submit', () => {
    progressBar.style.display = 'block';
});

/* Auto-refresh uploads table */
setInterval(() => {
    if (!document.hidden && sections.upload.classList.contains('active')) {
        window.location.reload();
    }
}, 5000);

/* Logs fetch */
async function fetchLogs() {
    const box = document.getElementById('logsBox');
    try {
        const res = await fetch('{{ url_for("get_logs") }}');
        if (!res.ok) {
            box.textContent = 'Unable to load logs.';
            return;
        }
        const data = await res.json();
        box.textContent = data.logs || 'No logs available.';
    } catch (e) {
        box.textContent = 'Error loading logs.';
    }
}
</script>

</body>
</html>
'''

# ---------------------------
# HELPERS
# ---------------------------

def list_processed_files():
    """Return a flat list of files in PROCESSED_FOLDER with relative paths."""
    results = []
    for root, dirs, files in os.walk(PROCESSED_FOLDER):
        for name in files:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, PROCESSED_FOLDER)
            results.append({"name": name, "rel_path": rel_path})
    return results

# ---------------------------
# ROUTES
# ---------------------------

@app.route('/preview/<filename>')
def preview_file(filename):
    return send_from_directory(PREVIEW_FOLDER, filename)

# Recursive search so downloads work even in category subfolders
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

    target_path = os.path.join(PROCESSED_FOLDER, rel_path)
    if os.path.isfile(target_path):
        try:
            os.remove(target_path)
        except Exception:
            pass
    return redirect(url_for('upload_file', view='processed'))

@app.route('/logs')
def get_logs():
    if not LOG_FILE or not os.path.isfile(LOG_FILE):
        return jsonify({"logs": "No log file found."})
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        content = content[-8000:]
        return jsonify({"logs": content})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {e}"})


@app.route('/', methods=['GET', 'POST'])
def upload_file():
    view = request.args.get('view', 'upload')

    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part', 400

        file = request.files['file']
        if file.filename == '':
            return 'No selected file', 400

        # Save preview copy
        preview_path = os.path.join(PREVIEW_FOLDER, file.filename)
        file.save(preview_path)

        # Save temp copy for processing
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.stream.seek(0)
            file.save(tmp.name)
            tmp_path = tmp.name

        upload_record = {
            'filename': file.filename,
            'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'Processing',
            'category': None,
            'confidence': None,
            'summary': None,
            'preview': file.filename,
            'processed_filename': None,
        }
        uploads.append(upload_record)

        def process_file(path, record, original_name):
            try:
                # V6 deterministic pipeline
                result = classify_and_route_v6(path, config)

                record['status'] = 'Completed'
                if isinstance(result, dict):
                    record['category'] = result.get('category')
                    record['confidence'] = result.get('confidence')
                    record['summary'] = result.get('summary')

                    processed_name = (
                        result.get('final_filename')
                        or result.get('routed_filename')
                        or result.get('output_filename')
                    )
                else:
                    processed_name = None

                record['processed_filename'] = processed_name or original_name

            except Exception as e:
                record['status'] = 'Failed'
                record['summary'] = f'Error: {e}'

        threading.Thread(
            target=process_file,
            args=(tmp_path, upload_record, file.filename),
            daemon=True
        ).start()

        return redirect(url_for('upload_file'))

    # GET
    processed_files = list_processed_files()
    return render_template_string(
        HTML_TEMPLATE,
        uploads=uploads,
        processed_files=processed_files,
    )

# ---------------------------
# ENTRY POINT
# ---------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)



