

import threading
import http.server
import socketserver
import json
from datetime import datetime
import os

# Store last N events
MAX_EVENTS = 200
EVENTS = []


def add_event(event: dict):
    """Add a debug event to the in-memory buffer."""
    event["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    EVENTS.append(event)
    if len(EVENTS) > MAX_EVENTS:
        del EVENTS[0]


# -------------------------------------------------------------------
# HTML TEMPLATE (SAFE — NO .format() BRACES)
# -------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Smart Sorter V3 Debug Dashboard</title>
<style>
body { font-family: Consolas, monospace; background: #111; color: #eee; padding: 20px; }
h1 { color: #6cf; }
.event { border: 1px solid #444; padding: 10px; margin-bottom: 15px; background: #1a1a1a; }
.key { color: #6cf; }
.value { color: #eee; }
.section { margin-top: 10px; padding: 5px; border-left: 3px solid #6cf; }
</style>
</head>
<body>
<h1>Smart Sorter V3 Debug Dashboard</h1>
<p>Showing last {count} events</p>
{events_html}
</body>
</html>
"""


# -------------------------------------------------------------------
# Render a single event block
# -------------------------------------------------------------------
def render_event(e: dict) -> str:
    def fmt(k, v):
        return f"<div><span class='key'>{k}:</span> <span class='value'>{v}</span></div>"

    return f"""
<div class='event'>
    {fmt("Timestamp", e.get("timestamp"))}
    {fmt("Original File", e.get("original"))}
    {fmt("Final Category", e.get("category"))}
    {fmt("Gemini Category", e.get("gemini_category"))}
    {fmt("Smart Mode Category", e.get("smart_category"))}
    {fmt("Gemini Filename", e.get("gemini_filename"))}
    {fmt("V3 Filename", e.get("v3_filename"))}
    {fmt("Final Filename", e.get("final_filename"))}

    <div class='section'><b>Metadata</b><pre>{json.dumps(e.get("metadata", {}), indent=2)}</pre></div>
    <div class='section'><b>Reasoning</b><pre>{(e.get("reasoning") or "")}</pre></div>
    <div class='section'><b>Text (first 500 chars)</b><pre>{(e.get("text") or "")[:500]}</pre></div>
</div>
"""


# -------------------------------------------------------------------
# HTTP Handler
# -------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return

        # Build event HTML
        events_html = "\n".join(render_event(e) for e in reversed(EVENTS))

        # SAFE replacement — no .format() parsing
        html = (
            HTML_TEMPLATE
            .replace("{count}", str(len(EVENTS)))
            .replace("{events_html}", events_html)
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


# -------------------------------------------------------------------
# Start dashboard server (Codespaces-compatible)
# -------------------------------------------------------------------
def start_dashboard(host="0.0.0.0", port=8765):
    """Run the dashboard in a background thread."""
    def run():
        with socketserver.TCPServer((host, port), Handler) as httpd:

            # Detect Codespaces forwarded URL
            forwarded = None
            try:
                codespace = os.environ.get("CODESPACE_NAME")
                if codespace:
                    forwarded = f"https://{codespace}-{port}.githubpreview.dev"
            except Exception:
                forwarded = None

            if forwarded:
                print(f"[V3-DASH] Dashboard running at {forwarded}")
            else:
                print(f"[V3-DASH] Dashboard running at http://{host}:{port}")

            httpd.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()
