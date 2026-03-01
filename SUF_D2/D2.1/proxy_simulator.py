from __future__ import annotations

import glob
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

HOST = "127.0.0.1"
PORT = 11096
API_PREFIX = "/v1"

app = Flask(__name__)
workflow_running = None

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
            "running": True,
            "message": "Workflow started",
        },
    },
    "stop-workflow": {
        "method": "POST",
        "path": f"{API_PREFIX}/stop-workflow",
        "description": "Simulate stopping a workflow.",
        "inputs": "None",
        "returns": {
            "ok": True,
            "status": "idle",
            "running": False,
            "message": "Workflow stopped",
        },
    },
    "status": {
        "method": "GET",
        "path": f"{API_PREFIX}/status",
        "description": "Current simulator workflow state.",
        "inputs": "None",
        "returns": {
            "ok": True,
            "status": "unknown | running | idle",
            "running": True,
        },
    },
    "check-files": {
        "method": "POST",
        "path": f"{API_PREFIX}/check-files",
        "description": "Check that configured file inputs exist. Wildcards are expanded on the proxy.",
        "inputs": {
            "path": "/base/directory",
            "files": ["run_001.h5", "run_*.h5"],
        },
        "returns": {
            "ok": True,
            "status": "success | failure",
            "path": "/base/directory",
            "requested": ["run_001.h5", "run_*.h5"],
            "found": [
                {
                    "file": "/base/directory/run_001.h5",
                    "size": 12345,
                    "modifiedTime": "2026-02-27T12:34:56Z",
                    "modifiedEpoch": 1761234567.123,
                }
            ],
            "missing": [],
            "foundCount": 1,
            "missingCount": 0,
        },
    },
    "check-ejfat-control-plane": {
        "method": "POST",
        "path": f"{API_PREFIX}/check-ejfat-control-plane",
        "description": "Simulate EJFAT control-plane connectivity check.",
        "inputs": {
            "transportType": "ejfat",
            "ejfat": {
                "loadBalancer": "esnet",
                "controlPlane": {
                    "ipv4": "...",
                    "ipv6": "...",
                    "ports": "...",
                },
                "dataPlane": {
                    "ipv4": "...",
                    "ipv6": "...",
                    "ports": "...",
                },
            },
        },
        "returns": {
            "ok": True,
            "status": "success",
            "message": "EJFAT control-plane connectivity check passed.",
            "checked": {
                "loadBalancer": "esnet",
                "controlPlane": {
                    "ipv4": "...",
                    "ipv6": "...",
                    "ports": "...",
                },
                "dataPlane": {
                    "ipv4": "...",
                    "ipv6": "...",
                    "ports": "...",
                },
            },
        },
    },
    "check-hpc-farm": {
        "method": "POST",
        "path": f"{API_PREFIX}/check-hpc-farm",
        "description": "Simulate HPC compute farm accessibility and capacity query.",
        "inputs": {
            "hpcCompute": {
                "location": "JLab/ifarm",
                "project": "proj123",
                "queue": "debug",
                "numJobs": "4",
                "cpusPerJob": "8",
                "wholeNode": False,
                "memory": "16G",
                "time": "00:30:00",
                "container": "image:tag",
                "model": "model-name",
            }
        },
        "returns": {
            "ok": True,
            "status": "success",
            "message": "HPC farm is accessible.",
            "farm": {
                "name": "ifarm-sim",
                "location": "JLab/ifarm",
                "nodes": 128,
                "cores": 8192,
                "jobSlots": 640,
                "runningJobs": 173,
            },
            "checked": {
                "location": "JLab/ifarm",
                "project": "proj123",
                "queue": "debug",
                "numJobs": "4",
                "cpusPerJob": "8",
                "wholeNode": False,
                "memory": "16G",
                "time": "00:30:00",
                "container": "image:tag",
                "model": "model-name",
            },
        },
    },
}


def _is_glob_pattern(value: str) -> bool:
    return any(ch in value for ch in ("*", "?", "["))


def _expand_requested_files(path_value: str, files_value: list[str]):
    base_dir = Path(path_value).expanduser().resolve()
    found: list[dict] = []
    missing: list[str] = []
    seen: set[str] = set()

    for raw_item in files_value:
        item = str(raw_item).strip()
        if not item:
            continue

        candidate_pattern = item if Path(item).is_absolute() else str(base_dir / item)
        is_pattern = _is_glob_pattern(item)

        if is_pattern:
            matched = [Path(match).resolve() for match in glob.glob(candidate_pattern) if Path(match).is_file()]
        else:
            candidate_path = Path(candidate_pattern).expanduser().resolve()
            matched = [candidate_path] if candidate_path.is_file() else []

        if not matched:
            missing.append(item)
            continue

        for file_path in sorted(matched):
            key = str(file_path)
            if key in seen:
                continue
            seen.add(key)

            stats = file_path.stat()
            found.append(
                {
                    "file": key,
                    "size": stats.st_size,
                    "modifiedTime": datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "modifiedEpoch": stats.st_mtime,
                }
            )

    ok = len(missing) == 0
    return {
        "ok": ok,
        "status": "success" if ok else "failure",
        "path": str(base_dir),
        "requested": [str(item).strip() for item in files_value if str(item).strip()],
        "found": found,
        "missing": missing,
        "foundCount": len(found),
        "missingCount": len(missing),
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
    return jsonify({"ok": True, "status": "running", "running": True, "message": "Workflow started"})


@app.post(f"{API_PREFIX}/stop-workflow")
def stop_workflow():
    global workflow_running
    workflow_running = False
    return jsonify({"ok": True, "status": "idle", "running": False, "message": "Workflow stopped"})


@app.get(f"{API_PREFIX}/status")
def status():
    if workflow_running is None:
        return jsonify({"ok": True, "status": "unknown", "running": False})

    return jsonify({"ok": True, "status": "running" if workflow_running else "idle", "running": workflow_running})


@app.post(f"{API_PREFIX}/check-files")
def check_files():
    payload = request.get_json(silent=True) or {}
    path_value = str(payload.get("path", "")).strip()
    files_value = payload.get("files", [])

    if not path_value:
        return jsonify({"ok": False, "status": "failure", "error": "Field 'path' is required."}), 400

    if not isinstance(files_value, list) or not files_value:
        return jsonify({"ok": False, "status": "failure", "error": "Field 'files' must be a non-empty list."}), 400

    base_dir = Path(path_value).expanduser().resolve()
    if not base_dir.exists() or not base_dir.is_dir():
        return (
            jsonify(
                {
                    "ok": False,
                    "status": "failure",
                    "error": f"Directory not found: {base_dir}",
                    "path": str(base_dir),
                    "requested": [str(item).strip() for item in files_value if str(item).strip()],
                    "found": [],
                    "missing": [str(item).strip() for item in files_value if str(item).strip()],
                    "foundCount": 0,
                    "missingCount": len([item for item in files_value if str(item).strip()]),
                }
            ),
            200,
        )

    return jsonify(_expand_requested_files(path_value, files_value))


@app.post(f"{API_PREFIX}/check-ejfat-control-plane")
def check_ejfat_control_plane():
    payload = request.get_json(silent=True) or {}
    ejfat = payload.get("ejfat", {}) if isinstance(payload.get("ejfat"), dict) else {}

    control_plane = ejfat.get("controlPlane", {}) if isinstance(ejfat.get("controlPlane"), dict) else {}
    data_plane = ejfat.get("dataPlane", {}) if isinstance(ejfat.get("dataPlane"), dict) else {}

    # Simulate REST connectivity check latency.
    time.sleep(2.0)

    return jsonify(
        {
            "ok": True,
            "status": "success",
            "message": "EJFAT control-plane connectivity check passed.",
            "checked": {
                "loadBalancer": ejfat.get("loadBalancer", ""),
                "controlPlane": {
                    "ipv4": control_plane.get("ipv4", ""),
                    "ipv6": control_plane.get("ipv6", ""),
                    "ports": control_plane.get("ports", ""),
                },
                "dataPlane": {
                    "ipv4": data_plane.get("ipv4", ""),
                    "ipv6": data_plane.get("ipv6", ""),
                    "ports": data_plane.get("ports", ""),
                },
            },
        }
    )


@app.post(f"{API_PREFIX}/check-hpc-farm")
def check_hpc_farm():
    payload = request.get_json(silent=True) or {}
    hpc = payload.get("hpcCompute", {}) if isinstance(payload.get("hpcCompute"), dict) else {}

    # Simulated accessibility check latency.
    time.sleep(1.5)

    location = str(hpc.get("location", "")).strip() or "JLab/ifarm"
    farm_name = "ifarm-sim" if "ifarm" in location.lower() else "hpc-farm-sim"

    return jsonify(
        {
            "ok": True,
            "status": "success",
            "message": "HPC farm is accessible.",
            "farm": {
                "name": farm_name,
                "location": location,
                "nodes": 128,
                "cores": 8192,
                "jobSlots": 640,
                "runningJobs": 173,
            },
            "checked": {
                "location": hpc.get("location", ""),
                "project": hpc.get("project", ""),
                "queue": hpc.get("queue", ""),
                "numJobs": hpc.get("numJobs", ""),
                "cpusPerJob": hpc.get("cpusPerJob", ""),
                "wholeNode": bool(hpc.get("wholeNode", False)),
                "memory": hpc.get("memory", ""),
                "time": hpc.get("time", ""),
                "container": hpc.get("container", ""),
                "model": hpc.get("model", ""),
            },
        }
    )


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
