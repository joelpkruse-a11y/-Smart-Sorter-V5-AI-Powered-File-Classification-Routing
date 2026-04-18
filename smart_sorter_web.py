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
/* --- styles omitted for brevity --- (include your full CSS block here) --- */
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

<h2>Upload Status</h2>
<table>
    <tr>
        <th>Filename</th><th>Uploaded</th><th>Status</th>
        <th>Category</th><th>Confidence</th><th>Summary</th><th>Preview</th>
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
themeToggle.addEventListener('click', () => body.classList.toggle('dark'));

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const dropText = document.getElementById('dropText');
const progressBar = document.getElementById('progressBar');
const uploadForm = document.getElementById('uploadForm');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); dropText.textContent = 'Release to upload'; });
dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('dragover'); dropText.textContent = 'Drop file here or click to select'; });
dropZone.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        dropText.textContent = e.dataTransfer.files[0].name;
    }
});
fileInput.addEventListener('change', () => { if (fileInput.files.length > 0) dropText.textContent = fileInput.files[0].name; });
uploadForm.addEventListener('submit', () => progressBar.style.display = 'block');
setInterval(() => { if (!document.hidden) window.location.reload(); }, 5000);
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

        preview_path = os.path.join(PREVIEW_FOLDER, file.filename)
        file.save(preview_path)

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

# --- Render-compatible entry point ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
