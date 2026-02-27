from __future__ import annotations

import time

from flask import Flask, jsonify

HOST = "127.0.0.1"
PORT = 11096

app = Flask(__name__)
workflow_running = False


@app.get("/")
def index():
        return """
<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Proxy Simulator API</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; color: #1f2937; }
            h1 { margin-bottom: 0.5rem; }
            code { background: #f3f4f6; padding: 0.1rem 0.35rem; border-radius: 0.3rem; }
            li { margin: 0.45rem 0; }
            .hint { color: #4b5563; }
        </style>
    </head>
    <body>
        <h1>Proxy Simulator API</h1>
        <p class=\"hint\">Available endpoints on 127.0.0.1:11096:</p>
        <ul>
            <li><code>GET /</code> — API index page</li>
            <li><code>GET /ping</code> — connectivity check</li>
            <li><code>POST /check-components</code> — simulate pre-launch component checks</li>
            <li><code>POST /run-workflow</code> — simulate workflow start</li>
            <li><code>GET /status</code> — simulator workflow state</li>
        </ul>
    </body>
</html>
"""


@app.get("/ping")
def ping():
    return jsonify({"ok": True, "service": "proxy-simulator", "host": HOST, "port": PORT})


@app.post("/check-components")
def check_components():
    time.sleep(0.2)
    return jsonify(
        {
            "ok": True,
            "status": "ready",
            "components": [
                {"name": "Instrument Gateway", "status": "Ready"},
                {"name": "Transfer Orchestrator", "status": "Ready"},
                {"name": "HPC Ingest Service", "status": "Ready"},
                {"name": "Monitoring Pipeline", "status": "Ready"},
            ],
        }
    )


@app.post("/run-workflow")
def run_workflow():
    global workflow_running
    workflow_running = True
    return jsonify({"ok": True, "status": "running", "message": "Workflow started"})


@app.get("/status")
def status():
    return jsonify({"ok": True, "status": "running" if workflow_running else "idle"})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
