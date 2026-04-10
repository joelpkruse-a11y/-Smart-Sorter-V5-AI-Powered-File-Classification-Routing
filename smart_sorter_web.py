import os
import tempfile
from datetime import datetime
from flask import (
    Flask, request, render_template_string,
    redirect, url_for, send_from_directory, jsonify
)

# Import your Render‑safe engine
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

# In‑memory upload history
uploads = []

# ---------------------------------------------------------
# HTML TEMPLATE – Material Hybrid (auto OS theme + toggle)
# ---------------------------------------------------------
HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smart Sorter V6 – Dashboard</title>

<!-- Material Icons -->
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded" rel="stylesheet">

<style>
:root {
    --bg: #0f172a;
    --bg-elevated: #111827;
    --bg-elevated-soft: #111827;
    --bg-soft: #020617;
    --border-subtle: rgba(148, 163, 184, 0.25);
    --accent: #3b82f6;
    --accent-soft: rgba(59, 130, 246, 0.12);
    --accent-strong: #2563eb;
    --accent-muted: #60a5fa;
    --text: #e5e7eb;
    --text-soft: #9ca3af;
    --text-softer: #6b7280;
    --danger: #f97373;
    --danger-soft: rgba(248, 113, 113, 0.12);
    --success: #4ade80;
    --success-soft: rgba(74, 222, 128, 0.12);
    --warning: #facc15;
    --warning-soft: rgba(250, 204, 21, 0.12);
    --shadow-soft: 0 18px 45px rgba(15, 23, 42, 0.75);
    --radius-lg: 18px;
    --radius-md: 12px;
    --radius-pill: 999px;
    --sidebar-width: 260px;
    --transition-fast: 0.18s ease-out;
    --transition-med: 0.24s ease;
    --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text",
                 "Segoe UI", sans-serif;
}

/* Light theme overrides */
:root[data-theme="light"] {
    --bg: #f3f4f6;
    --bg-elevated: #ffffff;
    --bg-elevated-soft: #f9fafb;
    --bg-soft: #e5e7eb;
    --border-subtle: rgba(148, 163, 184, 0.35);
    --accent: #2563eb;
    --accent-soft: rgba(37, 99, 235, 0.10);
    --accent-strong: #1d4ed8;
    --accent-muted: #3b82f6;
    --text: #111827;
    --text-soft: #4b5563;
    --text-softer: #6b7280;
    --danger: #dc2626;
    --danger-soft: rgba(220, 38, 38, 0.08);
    --success: #16a34a;
    --success-soft: rgba(22, 163, 74, 0.08);
    --warning: #ca8a04;
    --warning-soft: rgba(202, 138, 4, 0.08);
    --shadow-soft: 0 18px 45px rgba(15, 23, 42, 0.18);
}

/* Base layout */
*,
*::before,
*::after {
    box-sizing: border-box;
}

html, body {
    margin: 0;
    padding: 0;
    height: 100%;
    font-family: var(--font-sans);
    background: radial-gradient(circle at top left, #1e293b 0, var(--bg) 45%, #020617 100%);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
}

body {
    display: flex;
}

/* Sidebar */
.sidebar {
    width: var(--sidebar-width);
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(15, 23, 42, 0.96));
    border-right: 1px solid rgba(148, 163, 184, 0.25);
    box-shadow: 18px 0 45px rgba(15, 23, 42, 0.85);
    padding: 20px 18px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 10;
}

.sidebar-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 10px 6px;
    border-radius: var(--radius-md);
    background: radial-gradient(circle at top left, rgba(59, 130, 246, 0.18), transparent 55%);
}

.sidebar-logo {
    width: 40px;
    height: 40px;
    border-radius: 14px;
    background: radial-gradient(circle at 30% 20%, #60a5fa, #1d4ed8);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #eff6ff;
    font-weight: 700;
    font-size: 18px;
    box-shadow: 0 10px 25px rgba(37, 99, 235, 0.65);
}

.sidebar-title {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.sidebar-title span:first-child {
    font-size: 14px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-softer);
}

.sidebar-title span:last-child {
    font-size: 18px;
    font-weight: 600;
}

/* Nav */
.sidebar-nav {
    margin-top: 4px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.nav-section-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--text-softer);
    padding: 0 10px;
    margin-bottom: 4px;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 10px;
    border-radius: 999px;
    color: var(--text-soft);
    font-size: 14px;
    cursor: pointer;
    transition: background var(--transition-fast), color var(--transition-fast), transform 0.12s ease-out;
}

.nav-item:hover {
    background: rgba(148, 163, 184, 0.12);
    color: var(--text);
    transform: translateX(2px);
}

.nav-item.active {
    background: var(--accent-soft);
    color: var(--accent-muted);
    box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.35);
}

.nav-item .icon {
    width: 24px;
    height: 24px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: radial-gradient(circle at 30% 20%, rgba(59, 130, 246, 0.35), transparent 60%);
    color: var(--accent-muted);
    font-size: 18px;
}

.material-icon {
    font-family: "Material Symbols Rounded";
    font-weight: 400;
    font-style: normal;
    font-size: 20px;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    -webkit-font-feature-settings: "liga";
    -webkit-font-smoothing: antialiased;
}

/* Sidebar footer */
.sidebar-footer {
    margin-top: auto;
    padding: 10px 10px 6px;
    border-radius: var(--radius-md);
    background: radial-gradient(circle at bottom right, rgba(59, 130, 246, 0.18), transparent 55%);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 11px;
    color: var(--text-softer);
}

.theme-toggle {
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(15, 23, 42, 0.85);
    color: var(--text-soft);
    padding: 4px 10px;
    font-size: 11px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    transition: background var(--transition-fast), border var(--transition-fast), color var(--transition-fast), transform 0.12s ease-out;
}

.theme-toggle:hover {
    background: rgba(30, 64, 175, 0.9);
    border-color: rgba(129, 140, 248, 0.9);
    color: #e5e7eb;
    transform: translateY(-1px);
}

/* Main layout */
.main {
    margin-left: var(--sidebar-width);
    padding: 22px 26px 26px;
    width: calc(100% - var(--sidebar-width));
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    gap: 18px;
}

/* Section header */
.section-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 4px;
}

.section-header h2 {
    margin: 0;
    font-size: 22px;
    letter-spacing: 0.02em;
}

.section-header .subtitle {
    font-size: 13px;
    color: var(--text-soft);
}

/* Cards */
.upload-box,
.table-card,
.logs-box {
    background: radial-gradient(circle at top left, rgba(15, 23, 42, 0.9), rgba(15, 23, 42, 0.98));
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-subtle);
    box-shadow: var(--shadow-soft);
    padding: 18px 18px 16px;
}

:root[data-theme="light"] .upload-box,
:root[data-theme="light"] .table-card,
:root[data-theme="light"] .logs-box {
    background: var(--bg-elevated);
}

/* Upload box */
.upload-box h3 {
    margin: 0 0 4px;
    font-size: 16px;
}

.muted {
    color: var(--text-softer);
    font-size: 12px;
}

.drop-zone {
    margin-top: 12px;
    border-radius: var(--radius-md);
    border: 1px dashed rgba(148, 163, 184, 0.6);
    background: radial-gradient(circle at top left, rgba(30, 64, 175, 0.25), rgba(15, 23, 42, 0.95));
    padding: 22px 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-soft);
    font-size: 13px;
    cursor: pointer;
    transition: border var(--transition-fast), background var(--transition-fast), transform 0.12s ease-out;
}

.drop-zone:hover {
    border-color: rgba(129, 140, 248, 0.9);
    background: radial-gradient(circle at top left, rgba(37, 99, 235, 0.35), rgba(15, 23, 42, 0.98));
    transform: translateY(-1px);
}

.drop-zone input[type="file"] {
    display: none;
}

.upload-btn {
    margin-top: 12px;
    border-radius: var(--radius-pill);
    border: none;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 500;
    background: linear-gradient(135deg, var(--accent), var(--accent-strong));
    color: #eff6ff;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 12px 30px rgba(37, 99, 235, 0.65);
    transition: transform 0.12s ease-out, box-shadow 0.12s ease-out, filter 0.12s ease-out;
}

.upload-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 40px rgba(37, 99, 235, 0.75);
    filter: brightness(1.03);
}

/* Progress bar */
.progress-bar {
    margin-top: 10px;
    width: 100%;
    height: 4px;
    border-radius: 999px;
    background: rgba(30, 64, 175, 0.35);
    overflow: hidden;
    display: none;
}

.progress-inner {
    width: 0%;
    height: 100%;
    background: linear-gradient(90deg, #22c55e, #3b82f6);
    transition: width 0.18s ease-out;
}

/* Sections */
.section {
    display: none;
}

.section.active {
    display: block;
}

/* Table */
.table-card h3 {
    margin: 0 0 10px;
    font-size: 15px;
}

.table-card table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}

.table-card th,
.table-card td {
    padding: 8px 8px;
    border-bottom: 1px solid rgba(30, 64, 175, 0.35);
    vertical-align: top;
}

.table-card th {
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-softer);
}

.table-card tr:last-child td {
    border-bottom: none;
}

/* Summary cell */
.summary-cell {
    max-width: 260px;
    white-space: normal;
    word-wrap: break-word;
    color: var(--text-soft);
}

/* Status badges */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 500;
}

.status-badge.completed {
    background: var(--success-soft);
    color: var(--success);
}

.status-badge.processing {
    background: var(--warning-soft);
    color: var(--warning);
}

.status-badge.failed {
    background: var(--danger-soft);
    color: var(--danger);
}

/* Category tag */
.category-tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 11px;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(148, 163, 184, 0.35);
    color: var(--text-soft);
}

/* Download / Delete buttons */
.download-btn,
.delete-btn {
    border-radius: 999px;
    border: none;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    text-decoration: none;
    transition: background var(--transition-fast), transform 0.12s ease-out, box-shadow 0.12s ease-out;
}

.download-btn {
    background: rgba(37, 99, 235, 0.12);
    color: var(--accent-muted);
    border: 1px solid rgba(59, 130, 246, 0.45);
}

.download-btn:hover {
    background: rgba(37, 99, 235, 0.22);
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(37, 99, 235, 0.45);
}

.delete-btn {
    background: rgba(220, 38, 38, 0.08);
    color: var(--danger);
    border: 1px solid rgba(248, 113, 113, 0.45);
}

.delete-btn:hover {
    background: rgba(220, 38, 38, 0.16);
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(220, 38, 38, 0.45);
}

/* File list */
.file-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 360px;
    overflow-y: auto;
}

.file-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-radius: var(--radius-md);
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(30, 64, 175, 0.45);
    font-size: 12px;
}

:root[data-theme="light"] .file-row {
    background: var(--bg-elevated-soft);
}

.file-row .path {
    font-size: 11px;
    color: var(--text-softer);
}

/* Logs */
.logs-box {
    min-height: 220px;
    font-family: "SF Mono", ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 11px;
    color: var(--text-soft);
    white-space: pre-wrap;
    overflow-y: auto;
}

/* Preview thumbnails */
.preview-img {
    width: 120px;
    height: auto;
    max-height: 120px;
    object-fit: contain;
    border-radius: 10px;
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(30, 64, 175, 0.65);
    background: #020617;
}

.preview-cell {
    width: 140px;
    text-align: center;
    vertical-align: middle;
}

/* Responsive */
@media (max-width: 900px) {
    .sidebar {
        display: none;
    }
    .main {
        margin-left: 0;
        width: 100%;
        padding: 16px;
    }
}

/* OS theme auto-detect base */
@media (prefers-color-scheme: light) {
    :root:not([data-theme]) {
        color-scheme: light;
    }
}
@media (prefers-color-scheme: dark) {
    :root:not([data-theme]) {
        color-scheme: dark;
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
            <span class="icon">
                <span class="material-icon">cloud_upload</span>
            </span>
            <span>Upload & Status</span>
        </div>
        <div class="nav-item" data-section="processed">
            <span class="icon">
                <span class="material-icon">folder_open</span>
            </span>
            <span>Processed Files</span>
        </div>
        <div class="nav-item" data-section="logs">
            <span class="icon">
                <span class="material-icon">article</span>
            </span>
            <span>Logs</span>
        </div>
    </div>

    <div class="sidebar-footer">
        <span>Render · Flask</span>
        <button class="theme-toggle" id="themeToggle">
            <span class="material-icon" id="themeIcon">dark_mode</span>
            <span id="themeLabel">Auto</span>
        </button>
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
            <form id="uploadForm" action="/" method="post" enctype="multipart/form-data">
                <label class="drop-zone" id="dropZone">
                    <span id="dropText">Drop file here or click to select</span>
                    <input type="file" name="file" id="fileInput" required>
                </label>
                <button type="submit" class="upload-btn">
                    <span class="material-icon">play_arrow</span>
                    <span>Upload to Smart Sorter</span>
                </button>
                <div class="progress-bar" id="progressBar"><div class="progress-inner"></div></div>
            </form>
        </div>

        <div class="table-card" style="margin-top: 16px;">
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
                            <span class="status-badge completed">
                                <span class="material-icon">check_circle</span>
                                <span>Completed</span>
                            </span>
                        {% elif u.status == 'Processing' %}
                            <span class="status-badge processing">
                                <span class="material-icon">hourglass_top</span>
                                <span>Processing</span>
                            </span>
                        {% else %}
                            <span class="status-badge failed">
                                <span class="material-icon">error</span>
                                <span>{{ u.status }}</span>
                            </span>
                        {% endif %}
                    </td>

                    <td>
                        <span class="category-tag">
                            <span class="material-icon">label</span>
                            <span>{{ u.category or 'Pending' }}</span>
                        </span>
                    </td>

                    <td>{{ '%.2f'|format(u.confidence) if u.confidence is not none else 'N/A' }}</td>
                    <td class="summary-cell">{{ u.summary or 'Processing...' }}</td>

                    <td class="preview-cell">
                        {% if u.preview %}
                            <img src="{{ url_for('preview_file', filename=u.preview) }}" class="preview-img">
                        {% else %}
                            <span class="muted">No preview</span>
                        {% endif %}
                    </td>

                    <td>
                        {% if u.final_filename and u.status == 'Completed' %}
                            <a href="{{ url_for('download_processed', filename=u.final_filename) }}" class="download-btn">
                                <span class="material-icon">download</span>
                                <span>Download</span>
                            </a>
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
                            <a href="{{ url_for('download_processed', filename=f.rel_path) }}" class="download-btn">
                                <span class="material-icon">download</span>
                                <span>Download</span>
                            </a>
                            <form method="post" action="{{ url_for('delete_processed') }}" style="display:inline;">
                                <input type="hidden" name="filename" value="{{ f.name }}">
                                <input type="hidden" name="rel_path" value="{{ f.rel_path }}">
                                <button type="submit" class="delete-btn">
                                    <span class="material-icon">delete</span>
                                    <span>Delete</span>
                                </button>
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
// Theme handling: OS auto-detect + user override via localStorage
(function() {
    const root = document.documentElement;
    const stored = localStorage.getItem('smartSorterTheme'); // 'light', 'dark', or 'auto'
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    const themeLabel = document.getElementById('themeLabel');

    function applyTheme(mode) {
        if (mode === 'light') {
            root.setAttribute('data-theme', 'light');
            themeIcon.textContent = 'light_mode';
            themeLabel.textContent = 'Light';
        } else if (mode === 'dark') {
            root.setAttribute('data-theme', 'dark');
            themeIcon.textContent = 'dark_mode';
            themeLabel.textContent = 'Dark';
        } else {
            // auto
            root.removeAttribute('data-theme');
            const prefersDark = window.matchMedia &&
                window.matchMedia('(prefers-color-scheme: dark)').matches;
            if (prefersDark) {
                root.setAttribute('data-theme', 'dark');
                themeIcon.textContent = 'dark_mode';
            } else {
                root.setAttribute('data-theme', 'light');
                themeIcon.textContent = 'light_mode';
            }
            themeLabel.textContent = 'Auto';
        }
    }

    let currentMode = stored || 'auto';
    applyTheme(currentMode);

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            if (currentMode === 'auto') {
                currentMode = 'dark';
            } else if (currentMode === 'dark') {
                currentMode = 'light';
            } else {
                currentMode = 'auto';
            }
            localStorage.setItem('smartSorterTheme', currentMode);
            applyTheme(currentMode);
        });
    }

    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
            const storedMode = localStorage.getItem('smartSorterTheme') || 'auto';
            if (storedMode === 'auto') {
                applyTheme('auto');
            }
        });
    }
})();

// Navigation between sections
(function() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = {
        upload: document.getElementById('section-upload'),
        processed: document.getElementById('section-processed'),
        logs: document.getElementById('section-logs')
    };

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const section = item.getAttribute('data-section');
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            Object.keys(sections).forEach(key => {
                sections[key].classList.toggle('active', key === section);
            });
            if (section === 'logs') {
                fetchLogs();
            }
        });
    });
})();

// Upload form behavior
(function() {
    const form = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const dropZone = document.getElementById('dropZone');
    const dropText = document.getElementById('dropText');
    const progressBar = document.getElementById('progressBar');
    const progressInner = document.querySelector('.progress-inner');

    if (!form) return;

    dropZone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            dropText.textContent = fileInput.files[0].name;
        } else {
            dropText.textContent = 'Drop file here or click to select';
        }
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'rgba(129, 140, 248, 0.9)';
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'rgba(148, 163, 184, 0.6)';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'rgba(148, 163, 184, 0.6)';
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            dropText.textContent = fileInput.files[0].name;
        }
    });

    form.addEventListener('submit', () => {
        progressBar.style.display = 'block';
        progressInner.style.width = '20%';
        setTimeout(() => {
            progressInner.style.width = '60%';
        }, 200);
    });
})();

// Fetch logs
function fetchLogs() {
    const logsBox = document.getElementById('logsBox');
    if (!logsBox) return;
    logsBox.textContent = 'Loading logs…';
    fetch('/logs')
        .then(r => r.json())
        .then(data => {
            logsBox.textContent = data.logs || 'No logs available.';
        })
        .catch(() => {
            logsBox.textContent = 'Error loading logs.';
        });
}
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
    # 1) Treat `filename` as a relative path under PROCESSED_FOLDER
    candidate = os.path.join(PROCESSED_FOLDER, filename)
    if os.path.isfile(candidate):
        return send_from_directory(
            os.path.dirname(candidate),
            os.path.basename(candidate),
            as_attachment=True
        )

    # 2) Fallback: treat `filename` as a bare name and search recursively
    bare = os.path.basename(filename)
    for root, dirs, files in os.walk(PROCESSED_FOLDER):
        if bare in files:
            return send_from_directory(root, bare, as_attachment=True)

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
