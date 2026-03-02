from __future__ import annotations

import glob
import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

HOST = "127.0.0.1"
PORT = 11096
API_PREFIX = "/v1"

app = Flask(__name__)
workflow_running = None
workflow_started_at = None
worker_flow_delays_sec: list[float] = []
worker_to_aggregator_delays_sec: list[float] = []

SOURCE_TO_LB_DELAY_SEC = 1.5
WORKER_DELAY_MEAN_SEC = 1.5
WORKER_DELAY_STDDEV_SEC = 0.5
WORKER_DELAY_MIN_SEC = 1.0
WORKER_DELAY_MAX_SEC = 3.0
AGGREGATOR_TO_PLOT_DELAY_SEC = 1.5
PLOT_TO_VIEWER_DELAY_SEC = 1.5

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
    "workflow-metrics": {
        "method": "POST",
        "path": f"{API_PREFIX}/workflow-metrics",
        "description": "Simulate live workflow metrics for visualization.",
        "inputs": {
            "config": {
                "hpcCompute": {
                    "numJobs": "10",
                },
                "dataTransport": {
                    "type": "ejfat",
                },
            },
            "workerCount": 10,
            "ejfatEnabled": True,
        },
        "returns": {
            "ok": True,
            "status": "success",
            "running": True,
            "workflowState": "running | idle | unknown",
            "stats": {
                "throughputGbps": 21.5,
                "runningJobs": 8,
                "workerCount": 10,
            },
            "nodeStats": {
                "source": {
                    "framesPerSec": 215000,
                    "rateGbps": 21.5,
                },
            },
        },
    },
}


def _is_glob_pattern(value: str) -> bool:
    return any(ch in value for ch in ("*", "?", "["))


def _safe_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _ensure_worker_flow_delays(worker_count: int) -> list[float]:
    global worker_flow_delays_sec

    if len(worker_flow_delays_sec) == worker_count:
        return worker_flow_delays_sec

    sampled = []
    for _ in range(worker_count):
        delay = random.gauss(WORKER_DELAY_MEAN_SEC, WORKER_DELAY_STDDEV_SEC)
        sampled.append(_clamp(delay, WORKER_DELAY_MIN_SEC, WORKER_DELAY_MAX_SEC))

    worker_flow_delays_sec = sampled
    return worker_flow_delays_sec


def _ensure_worker_to_aggregator_delays(worker_count: int) -> list[float]:
    global worker_to_aggregator_delays_sec

    if len(worker_to_aggregator_delays_sec) == worker_count:
        return worker_to_aggregator_delays_sec

    sampled = []
    for _ in range(worker_count):
        delay = random.gauss(WORKER_DELAY_MEAN_SEC, WORKER_DELAY_STDDEV_SEC)
        sampled.append(_clamp(delay, WORKER_DELAY_MIN_SEC, WORKER_DELAY_MAX_SEC))

    worker_to_aggregator_delays_sec = sampled
    return worker_to_aggregator_delays_sec


def _current_flow_activation(worker_count: int):
    global workflow_started_at

    if workflow_running is not True or workflow_started_at is None:
        return {
            "elapsedSec": 0.0,
            "sourceActive": False,
            "workerIngressActive": [False for _ in range(worker_count)],
            "workerIngressStartSec": [0.0 for _ in range(worker_count)],
            "workerEgressActive": [False for _ in range(worker_count)],
            "workerEgressStartSec": [0.0 for _ in range(worker_count)],
            "aggregatorActive": False,
            "aggregatorStartSec": 0.0,
            "plotterActive": False,
            "plotterStartSec": 0.0,
            "viewerActive": False,
            "viewerStartSec": 0.0,
        }

    elapsed = max(0.0, time.time() - workflow_started_at)
    source_active = elapsed >= SOURCE_TO_LB_DELAY_SEC
    worker_ingress_delays = _ensure_worker_flow_delays(worker_count)
    worker_egress_delays = _ensure_worker_to_aggregator_delays(worker_count)

    worker_ingress_active = []
    worker_ingress_start_sec = []
    worker_egress_active = []
    worker_egress_start_sec = []

    for i in range(worker_count):
        ingress_start = SOURCE_TO_LB_DELAY_SEC + worker_ingress_delays[i]
        worker_ingress_start_sec.append(ingress_start)
        ingress_active = source_active and elapsed >= ingress_start
        worker_ingress_active.append(ingress_active)

        egress_start = ingress_start + worker_egress_delays[i]
        worker_egress_start_sec.append(egress_start)
        egress_active = ingress_active and elapsed >= egress_start
        worker_egress_active.append(egress_active)

    first_worker_egress_start = min(worker_egress_start_sec) if worker_egress_start_sec else float("inf")
    aggregator_start_sec = first_worker_egress_start if first_worker_egress_start != float("inf") else 0.0
    aggregator_active = elapsed >= aggregator_start_sec if source_active and worker_count > 0 else False

    plotter_start_sec = aggregator_start_sec + AGGREGATOR_TO_PLOT_DELAY_SEC if aggregator_active or aggregator_start_sec > 0 else 0.0
    plotter_active = elapsed >= plotter_start_sec if plotter_start_sec > 0 else False

    viewer_start_sec = plotter_start_sec + PLOT_TO_VIEWER_DELAY_SEC if plotter_start_sec > 0 else 0.0
    viewer_active = elapsed >= viewer_start_sec if viewer_start_sec > 0 else False

    return {
        "elapsedSec": elapsed,
        "sourceActive": source_active,
        "workerIngressActive": worker_ingress_active,
        "workerIngressStartSec": worker_ingress_start_sec,
        "workerEgressActive": worker_egress_active,
        "workerEgressStartSec": worker_egress_start_sec,
        "aggregatorActive": aggregator_active,
        "aggregatorStartSec": aggregator_start_sec,
        "plotterActive": plotter_active,
        "plotterStartSec": plotter_start_sec,
        "viewerActive": viewer_active,
        "viewerStartSec": viewer_start_sec,
    }


def _build_workflow_metrics(config: dict, worker_count: int, ejfat_enabled: bool):
    global workflow_running

    now = time.time()
    activation = _current_flow_activation(worker_count)
    elapsed = float(activation.get("elapsedSec", 0.0))
    source_active = bool(activation.get("sourceActive", False))
    worker_ingress_active_flags = activation.get("workerIngressActive", [False for _ in range(worker_count)])
    worker_ingress_start_sec = activation.get("workerIngressStartSec", [0.0 for _ in range(worker_count)])
    worker_egress_active_flags = activation.get("workerEgressActive", [False for _ in range(worker_count)])
    worker_egress_start_sec = activation.get("workerEgressStartSec", [0.0 for _ in range(worker_count)])
    aggregator_active = bool(activation.get("aggregatorActive", False))
    plotter_active = bool(activation.get("plotterActive", False))
    viewer_active = bool(activation.get("viewerActive", False))

    active = 1.0 if source_active else 0.0
    active_worker_ingress_count = sum(1 for is_active in worker_ingress_active_flags if is_active)
    active_worker_egress_count = sum(1 for is_active in worker_egress_active_flags if is_active)

    if active_worker_egress_count > 0:
        running_jobs = max(
            1,
            min(
                active_worker_egress_count,
                int(round(active_worker_egress_count * (0.72 + 0.18 * (math.sin(now / 10.0) + 1) / 2.0))),
            ),
        )
    else:
        running_jobs = 0

    src_rate_gbps = active * (19.5 + 2.2 * math.sin(now / 4.0))
    lb_efficiency = 0.96 + 0.02 * math.sin(now / 9.0)
    if active > 0 and active_worker_ingress_count > 0:
        split_rate = max(0.2, src_rate_gbps * lb_efficiency / active_worker_ingress_count)
    else:
        split_rate = 0.0

    hist_merge_rate = max(12.0, split_rate * active_worker_egress_count * 76.0) if aggregator_active else 0.0
    images_per_min = max(1.0, 8.0 + 3.0 * (math.sin(now / 7.0) + 1.0)) if plotter_active else 0.0
    latest_image_age = max(0.3, 5.5 - 2.1 * (math.sin(now / 6.3) + 1.0) / 2.0) if viewer_active else 0.0

    node_stats = {
        "source": {
            "framesPerSec": int(src_rate_gbps * 11500),
            "rateGbps": round(src_rate_gbps, 2),
        },
        "aggregator": {
            "histogramsPerSec": round(hist_merge_rate, 1),
            "queueDepth": int(20 + 14 * (math.sin(now / 5.0) + 1.0)) if aggregator_active else 0,
        },
        "plotter": {
            "imagesPerMin": round(images_per_min, 1),
            "lastRenderMs": int(120 + 65 * (math.sin(now / 3.5) + 1.0)) if plotter_active else 0,
        },
        "viewer": {
            "latestImageAgeSec": round(latest_image_age, 1),
            "viewers": int(2 + 4 * (math.sin(now / 11.0) + 1.0)) if viewer_active else 0,
        },
    }

    if ejfat_enabled:
        node_stats["ejfat"] = {
            "outStreams": worker_count,
            "splitRateGbps": round(split_rate, 2),
            "imbalancePct": round(0.4 + 1.8 * (math.sin(now / 8.0) + 1.0) / 2.0, 2) if active_worker_ingress_count > 0 else 0.0,
        }

    for i in range(worker_count):
        worker_active = worker_ingress_active_flags[i] if i < len(worker_ingress_active_flags) else False
        worker_egress_active = worker_egress_active_flags[i] if i < len(worker_egress_active_flags) else False
        worker_scale = 0.93 + 0.12 * ((i % 3) / 3)
        node_stats[f"worker-{i + 1}"] = {
            "framesPerSec": int(split_rate * 10800 * worker_scale) if worker_active else 0,
            "inferenceMs": round(7.5 + 3.2 * (math.sin(now / (2.7 + (i % 3))) + 1.0), 2) if worker_egress_active else 0.0,
            "histFillPerSec": int(190 + 42 * (math.sin((now + i) / 4.8) + 1.0)) if worker_egress_active else 0,
        }

    link_stats = {}
    if ejfat_enabled:
        link_stats["source->ejfat"] = {"active": source_active}
        for i in range(worker_count):
            worker_id = f"worker-{i + 1}"
            ingress_active = worker_ingress_active_flags[i] if i < len(worker_ingress_active_flags) else False
            link_stats[f"ejfat->{worker_id}"] = {"active": ingress_active}
            egress_active = worker_egress_active_flags[i] if i < len(worker_egress_active_flags) else False
            link_stats[f"{worker_id}->aggregator"] = {"active": egress_active}
    else:
        for i in range(worker_count):
            worker_id = f"worker-{i + 1}"
            ingress_active = worker_ingress_active_flags[i] if i < len(worker_ingress_active_flags) else False
            link_stats[f"source->{worker_id}"] = {"active": ingress_active}
            egress_active = worker_egress_active_flags[i] if i < len(worker_egress_active_flags) else False
            link_stats[f"{worker_id}->aggregator"] = {"active": egress_active}

    link_stats["aggregator->plotter"] = {"active": plotter_active}
    link_stats["plotter->viewer"] = {"active": viewer_active}

    if workflow_running is True:
        state_text = "running"
    elif workflow_running is False:
        state_text = "idle"
    else:
        state_text = "unknown"

    return {
        "ok": True,
        "status": "success",
        "running": workflow_running is True,
        "workflowState": state_text,
        "stats": {
            "throughputGbps": round(src_rate_gbps, 2),
            "runningJobs": running_jobs,
            "workerCount": worker_count,
        },
        "delays": {
            "sourceToLoadBalancerSec": SOURCE_TO_LB_DELAY_SEC,
            "workerAfterLoadBalancerSec": [round(delay, 3) for delay in _ensure_worker_flow_delays(worker_count)],
            "workerToAggregatorSec": [round(delay, 3) for delay in _ensure_worker_to_aggregator_delays(worker_count)],
            "workerIngressStartTimesSec": [round(value, 3) for value in worker_ingress_start_sec],
            "workerEgressStartTimesSec": [round(value, 3) for value in worker_egress_start_sec],
            "aggregatorToPlotSec": AGGREGATOR_TO_PLOT_DELAY_SEC,
            "plotToViewerSec": PLOT_TO_VIEWER_DELAY_SEC,
            "aggregatorStartSec": round(float(activation.get("aggregatorStartSec", 0.0)), 3),
            "plotterStartSec": round(float(activation.get("plotterStartSec", 0.0)), 3),
            "viewerStartSec": round(float(activation.get("viewerStartSec", 0.0)), 3),
            "elapsedSec": round(elapsed, 3),
        },
        "linkStats": link_stats,
        "nodeStats": node_stats,
    }


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
    global workflow_running, workflow_started_at, worker_flow_delays_sec, worker_to_aggregator_delays_sec
    workflow_running = True
    workflow_started_at = time.time()
    worker_flow_delays_sec = []
    worker_to_aggregator_delays_sec = []
    return jsonify({"ok": True, "status": "running", "running": True, "message": "Workflow started"})


@app.post(f"{API_PREFIX}/stop-workflow")
def stop_workflow():
    global workflow_running, workflow_started_at, worker_flow_delays_sec, worker_to_aggregator_delays_sec
    workflow_running = False
    workflow_started_at = None
    worker_flow_delays_sec = []
    worker_to_aggregator_delays_sec = []
    return jsonify({"ok": True, "status": "idle", "running": False, "message": "Workflow stopped"})


@app.get(f"{API_PREFIX}/status")
def status():
    if workflow_running is None:
        return jsonify({"ok": True, "status": "unknown", "running": False})

    if workflow_running is True and workflow_started_at is not None:
        elapsed = max(0.0, time.time() - workflow_started_at)
        if elapsed < SOURCE_TO_LB_DELAY_SEC:
            return jsonify({"ok": True, "status": "idle", "running": False, "warmup": True, "elapsedSec": round(elapsed, 3)})

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


@app.post(f"{API_PREFIX}/workflow-metrics")
def workflow_metrics():
    payload = request.get_json(silent=True) or {}
    config = payload.get("config", {}) if isinstance(payload.get("config"), dict) else {}

    hpc = config.get("hpcCompute", {}) if isinstance(config.get("hpcCompute"), dict) else {}
    data_transport = config.get("dataTransport", {}) if isinstance(config.get("dataTransport"), dict) else {}

    default_workers = max(1, _safe_int(hpc.get("numJobs", 4), 4))
    worker_count = max(1, _safe_int(payload.get("workerCount", default_workers), default_workers))

    ejfat_default = str(data_transport.get("type", "")).strip().lower() == "ejfat"
    ejfat_enabled = bool(payload.get("ejfatEnabled", ejfat_default))

    return jsonify(_build_workflow_metrics(config, worker_count, ejfat_enabled))


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
