import os
import tempfile
import threading
from datetime import datetime

from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory

from smart_sorter_v5 import classify_and_route, load_config

app = Flask(__name__)

# Ensure preview folder exists
PREVIEW_FOLDER = os.path.join(os.path.dirname(__file__), "upload_previews")
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

# Load Smart Sorter config once
config = load_config()

# In-memory upload records (demo only)
uploads = []

HTML_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smart Sorter V5 – Upload</title>

<style>
    :root {
        --bg: #f4f6f8;
        --card-bg: #ffffff;
        --text: #2c3e50;
        --muted: #7f8c8d;
        --accent: #4b7bec;
        --accent-dark: #3867d6;
        --border: #dfe6e9;
        --shadow: 0 4px 20px rgba(0,0,0,0.08);
        --table-header-bg: #2c3e50;
        --table-header-text: #ffffff;
    }

    body.dark {
        --bg: #111827;
        --card-bg: #1f2933;
        --text: #e5e7eb;
        --muted: #9ca3af;
        --accent: #60a5fa;
        --accent-dark: #3b82f6;
        --border: #374151;
        --shadow: 0 4px 20px rgba(0,0,0,0.6);
        --table-header-bg: #111827;
        --table-header-text: #e5e7eb;
    }

    body {
        font-family: "Segoe UI", Roboto, sans-serif;
        background: var(--bg);
        margin: 0;
        padding: 40px;
        color: var(--text);
        transition: background 0.2s, color 0.2s;
    }

    h1 {
        text-align: center;
        font-size: 32px;
        margin-bottom: 10px;
    }

    h2 {
        margin-top: 40px;
    }

    .top-bar {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 16px;
        margin-bottom: 20px;
    }

    .toggle-btn {
        padding: 6px 14px;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: var(--card-bg);
        color: var(--text);
        cursor: pointer;
        font-size: 13px;
    }

    .upload-box {
        background: var(--card-bg);
        width: 520px;
        margin: 0 auto;
        padding: 25px;
        border-radius: 12px;
        box-shadow: var(--shadow);
        text-align: center;
        border: 1px solid var(--border);
    }

    .drop-zone {
        border: 2px dashed var(--border);
        border-radius: 10px;
        padding: 25px;
        margin-top: 10px;
        cursor: pointer;
        transition: 0.2s;
        color: var(--muted);
        font-size: 14px;
    }

    .drop-zone.dragover {
        border-color: var(--accent);
        background: rgba(75, 123, 236, 0.05);
        color: var(--accent);
    }

    input[type=file] {
        display: none;
    }

    .upload-btn {
        margin-top: 15px;
        background: var(--accent);
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 15px;
        transition: 0.2s;
    }

    .upload-btn:hover {
        background: var(--accent-dark);
    }

    .progress-bar {
        margin-top: 15px;
        width: 100%;
        height: 6px;
        border-radius: 999px;
        background: var(--border);
        overflow: hidden;
        display: none;
    }

    .progress-inner {
        width: 40%;
        height: 100%;
        background: var(--accent);
        border-radius: 999px;
        animation: progress-pulse 1.2s infinite ease-in-out;
    }

    @keyframes progress-pulse {
        0% { transform: translateX(-100%); }
        50% { transform: translateX(0%); }
        100% { transform: translateX(100%); }
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 25px;
        background: var(--card-bg);
        border-radius: 10px;
        overflow: hidden;
        box-shadow: var(--shadow);
    }

    th {
        background: var(--table-header-bg);
        color: var(--table-header-text);
        padding: 10px;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    td {
        padding: 10px;
        border-bottom: 1px solid var(--border);
        font-size: 13px;
        vertical-align: top;
    }

    tr:hover {
        background: rgba(148, 163, 184, 0.08);
    }

    .status-badge {
        padding: 4px 10px;
        border-radius: 999px;
        color: white;
        font-size: 11px;
        font-weight: 600;
    }

    .processing { background: #f39c12; }
    .completed { background: #27ae60; }
    .failed { background: #e74c3c; }

    .category-tag {
        padding: 4px 8px;
        border-radius: 6px;
        background: rgba(148, 163, 184, 0.25);
        font-size: 11px;
        display: inline-block;
    }

    .summary-cell {
        max-width: 260px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .muted {
        color: var(--muted);
        font-size: 12px;
    }

    .preview-img {
        width: 80px;
        height: auto;
        border-radius: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        object-fit: cover;
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

        <div class="progress-bar" id="progressBar">
            <div class="progress-inner"></div>
        </div>
    </form>
</div>

<h2>Upload Status</h2>

<table>
    <tr>
        <th>Filename</th>
        <th>Uploaded</th>
        <th>Status</th>
        <th>Category</th>
        <th>Confidence</th>
        <th>Summary</th>
        <th>Preview</th>
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

        <td>
            {% if u.category %}
                <span class="category-tag">{{ u.category }}</span>
            {% else %}
                <span class="category-tag">Pending</span>
            {% endif %}
        </td>

        <td>
            {% if u.confidence is not none %}
                {{ '%.2f'|format(u.confidence) }}
            {% else %}
                N/A
            {% endif %}
        </td>

        <td class="summary-cell">
            {{ u.summary or 'Processing...' }}
        </td>

        <td>
            {% if u.preview and (u.preview.lower().endswith('.jpg')
                or u.preview.lower().endswith('.jpeg')
                or u.preview.lower().endswith('.png')
                or u.preview.lower().endswith('.webp')) %}
                <img src="{{ url_for('preview_file', filename=u.preview) }}" class="preview-img">
            {% else %}
                <span class="muted">No preview</span>
            {% endif %}
        </td>
    </tr>
    {% endfor %}
</table>

<script>
    const body = document.body;
    const themeToggle = document.getElementById('themeToggle');
    themeToggle.addEventListener('click', () => {
        body.classList.toggle('dark');
    });

    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const dropText = document.getElementById('dropText');
    const progressBar = document.getElementById('progressBar');
    const uploadForm = document.getElementById('uploadForm');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
        dropText.textContent = 'Release to upload';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
        dropText.textContent = 'Drop file here or click to select';
    });

    dropZone.addEventListener('drop', (e) => {
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
        if (!document.hidden) {
            window.location.reload();
        }
    }, 5000);
</script>

</body>
</html>
'''

@app.route('/preview/<filename>')
def preview_file(filename):
    return send_from_directory(PREVIEW_FOLDER, filename)

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part', 400

        file = request.files['file']
        if file.filename == '':
            return 'No selected file', 400

        # Save a copy for preview (with original filename)
        preview_path = os.path.join(PREVIEW_FOLDER, file.filename)
        file.save(preview_path)

        # Save a temp copy for Smart Sorter processing
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
        }
        uploads.append(upload_record)

        def process_file(path, record):
            try:
                # If you update classify_and_route to return details, capture them here.
                # For now, we just call it and set demo values.
                classify_and_route(path, config)

                record['status'] = 'Completed'
                record['category'] = record.get('category') or 'ExampleCategory'
                record['confidence'] = record.get('confidence') or 0.95
                record['summary'] = record.get('summary') or 'Document processed successfully.'
            except Exception as e:
                record['status'] = 'Failed'
                record['summary'] = f'Error: {e}'

        threading.Thread(target=process_file, args=(tmp_path, upload_record), daemon=True).start()

        return redirect(url_for('upload_file'))

    return render_template_string(HTML_TEMPLATE, uploads=uploads)

if __name__ == '__main__':
    app.run(port=5000, debug=True)
