from __future__ import annotations

import json
import time

from flask import Flask, jsonify

HOST = "127.0.0.1"
PORT = 11096
API_PREFIX = "/v1"

app = Flask(__name__)
workflow_running = False

ENDPOINT_DOCS = {
    "ping": {
        "method": "GET",
        "path": f"{API_PREFIX}/ping",
        "description": "Connectivity check for proxy simulator.",
        "inputs": "None",
        "returns": {
            "ok": True,
            "service": "proxy-simulator",
            "host": HOST,
            "port": PORT,
        },
    },
    "check-components": {
        "method": "POST",
        "path": f"{API_PREFIX}/check-components",
        "description": "Simulate pre-launch component checks.",
        "inputs": "None",
        "returns": {
            "ok": True,
            "status": "ready",
            "components": [
                {"name": "Instrument Gateway", "status": "Ready"},
                {"name": "Transfer Orchestrator", "status": "Ready"},
                {"name": "HPC Ingest Service", "status": "Ready"},
                {"name": "Monitoring Pipeline", "status": "Ready"},
            ],
        },
    },
    "run-workflow": {
        "method": "POST",
        "path": f"{API_PREFIX}/run-workflow",
        "description": "Simulate starting a workflow.",
        "inputs": "None",
        "returns": {
            "ok": True,
            "status": "running",
            "message": "Workflow started",
        },
    },
    "status": {
        "method": "GET",
        "path": f"{API_PREFIX}/status",
        "description": "Current simulator workflow state.",
        "inputs": "None",
        "returns": {
            "ok": True,
            "status": "running | idle",
        },
    },
}


@app.get("/")
def index():
    endpoint_rows = "\n".join(
        [
            "<li>"
            "<details>"
            f"<summary><code>{doc['method']} {doc['path']}</code></summary>"
            f"<p>{doc['description']}</p>"
            "<div class=\"label\">Inputs</div>"
            f"<pre>{doc['inputs']}</pre>"
            "<div class=\"label\">Return value (JSON example)</div>"
            f"<pre>{json.dumps(doc['returns'], indent=2)}</pre>"
            f"<p><a href=\"{doc['path']}\" target=\"_blank\" rel=\"noopener noreferrer\">Try endpoint</a></p>"
            "</details>"
            "</li>"
            for _, doc in ENDPOINT_DOCS.items()
        ]
    )

    return f"""
<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Proxy Simulator API</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; color: #1f2937; }}
            h1 {{ margin-bottom: 0.5rem; }}
            code {{ background: #f3f4f6; padding: 0.1rem 0.35rem; border-radius: 0.3rem; }}
            li {{ margin: 0.65rem 0; }}
            details {{ background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.5rem 0.75rem; }}
            summary {{ cursor: pointer; font-weight: 600; }}
            pre {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.9rem; overflow-x: auto; }}
            .label {{ color: #4b5563; font-weight: 600; margin-top: 1rem; }}
            .hint {{ color: #4b5563; }}
        </style>
    </head>
    <body>
        <h1>Proxy Simulator API</h1>
        <p class=\"hint\">Available v1 endpoints on {HOST}:{PORT} (click to expand):</p>
        <ul>
            <li><code>GET /</code> — API index page</li>
            {endpoint_rows}
        </ul>
    </body>
</html>
"""


@app.get(f"{API_PREFIX}/ping")
def ping():
    return jsonify({"ok": True, "service": "proxy-simulator", "host": HOST, "port": PORT})


@app.post(f"{API_PREFIX}/check-components")
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


@app.post(f"{API_PREFIX}/run-workflow")
def run_workflow():
    global workflow_running
    workflow_running = True
    return jsonify({"ok": True, "status": "running", "message": "Workflow started"})


@app.get(f"{API_PREFIX}/status")
def status():
    return jsonify({"ok": True, "status": "running" if workflow_running else "idle"})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
