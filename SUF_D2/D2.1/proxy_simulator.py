from __future__ import annotations

import time

from flask import Flask, jsonify

HOST = "127.0.0.1"
PORT = 11096

app = Flask(__name__)
workflow_running = False


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
