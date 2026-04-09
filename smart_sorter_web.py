import os
import tempfile
import threading
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory
from smart_sorter_v5 import classify_and_route, load_config

app = Flask(__name__)

# Load Smart Sorter config once
config = load_config()

# Folders from config
INCOMING_FOLDER = config["paths"]["incoming"]
PROCESSED_FOLDER = config["paths"]["processed"]

# Ensure preview folder exists (for UI thumbnails)
PREVIEW_FOLDER = os.path.join(os.path.dirname(__file__), "upload_previews")
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

# In-memory upload records (demo only)
uploads = []

# ---------------------------
# HTML TEMPLATE
# ---------------------------
HTML_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smart Sorter V5 – Upload</title>

<style>
/* --- styles omitted for brevity --- */

body {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 0;
    padding: 0;
    background: #f5f5f7;
    color: #111827;
}

body.dark {
    background: #0b1120;
    color: #e5e7eb;
}

.top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 24px;
    background: #111827;
    color: #f9fafb;
}

.top-bar h1 {
    margin: 0;
    font-size: 1.25rem;
}

.toggle-btn {
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid #4b5563;
    background: #111827;
    color: #e5e7eb;
    cursor: pointer;
    font-size: 0.85rem;
}

.upload-box {
    max-width: 640px;
    margin: 24px auto;
    padding: 24px;
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.08);
}

body.dark .upload-box {
    background: #020617;
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.9);
}

.upload-box h2 {
    margin-top: 0;
    margin-bottom: 8px;
}

.muted {
    color: #6b7280;
    font-size: 0.85rem;
}

body.dark .muted {
    color: #9ca3af;
}

.drop-zone {
    margin-top: 16px;
    border: 2px dashed #9ca3af;
    border-radius: 12px;
    padding: 32px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s ease, background 0.2s ease;
}

.drop-zone.dragover {
    border-color: #4f46e5;
    background: rgba(79, 70, 229, 0.06);
}

.drop-zone input[type="file"] {
    display: none;
}

.upload-btn {
    margin-top: 16px;
    padding: 10px 18px;
    border-radius: 999px;
    border: none;
    background: #4f46e5;
    color: #f9fafb;
    font-weight: 500;
    cursor: pointer;
}

.upload-btn:hover {
    background: #4338ca;
}

.progress-bar {
    margin-top: 12px;
    width: 100%;
    height: 6px;
    border-radius: 999px;
    background: #e5e7eb;
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

table {
    width: 95%;
    margin: 0 auto 32px auto;
    border-collapse: collapse;
    font-size: 0.9rem;
}

th, td {
    padding: 8px 10px;
    border-bottom: 1px solid #e5e7eb;
    text-align: left;
    vertical-align: top;
}

body.dark th, body.dark td {
    border-color: #1f2937;
}

th {
    background: #f3f4f6;
    font-weight: 600;
}

body.dark th {
    background: #020617;
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
    background: #dcfce7;
    color: #166534;
}

.status-badge.processing {
    background: #e0f2fe;
    color: #075985;
}

.status-badge.failed {
    background: #fee2e2;
    color: #991b1b;
}

.category-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    background: #eef2ff;
    color: #3730a3;
    font-size: 0.75rem;
}

.summary-cell {
    max-width: 260px;
    white-space: normal;
}

.preview-img {
    max-width: 80px;
    max-height: 80px;
    border-radius: 6px;
    object-fit: cover;
    border: 1px solid #e5e7eb;
}

.download-btn {
    padding: 6px 12px;
    background: #4a90e2;
    color: white;
    border-radius: 4px;
    text-decoration: none;
    font-size: 0.85rem;
}
.download-btn:hover {
    background: #357ab8;
}
</style>
</head>

<body>
<div class="top-bar">
    <h1>Smart Sorter V5</h1>
    <button class="toggle-btn" id="themeToggle">Toggle Dark Mode</button>
</div>

<div class="upload-box">
    <h2>Upload a File</h2>
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

<h2 style="margin-left: 2.5%;">Upload Status</h2>
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
        <td>{{ '%.2f'|format(u.confidence) if u.confidence else 'N/A' }}</td>
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

<script>
const body = document.body;
document.getElementById('themeToggle').addEventListener('click', () => {
    body.classList.toggle('dark');
});

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
setInterval(() => {
    if (!document.hidden) window.location.reload();
}, 5000);
</script>

</body>
</html>
'''

# ---------------------------
# ROUTES
# ---------------------------

@app.route('/preview/<filename>')
def preview_file(filename):
    return send_from_directory(PREVIEW_FOLDER, filename)

# FIXED: recursive search so downloads work even in category subfolders
@app.route('/download/<path:filename>')
def download_processed(filename):
    for root, dirs, files in os.walk(PROCESSED_FOLDER):
        if filename in files:
            return send_from_directory(root, filename, as_attachment=True)
    return "File not found", 404

@app.route('/', methods=['GET', 'POST'])
def upload_file():
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
                result = classify_and_route(path, config)

                record['status'] = 'Completed'
                record['category'] = result.get('category')
                record['confidence'] = result.get('confidence')
                record['summary'] = result.get('summary')

                # Try all possible filename keys
                processed_name = (
                    result.get('final_filename')
                    or result.get('routed_filename')
                    or result.get('output_filename')
                )

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

    return render_template_string(HTML_TEMPLATE, uploads=uploads)

# ---------------------------
# ENTRY POINT
# ---------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

