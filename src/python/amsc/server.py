"""
Minimal Flask REST API for managing SLURM distributed jobs.
 
Endpoints:
  POST /jobs              body: {"nworkers": int}        -> {"job_id": str}
  DELETE /jobs/<job_id>                                  -> {}
  GET  /jobs/<job_id>                                    -> {"ejfat_uri_in": str,
                                                             "ejfat_uri_out": str,
                                                             "running": bool}
 
State is in-process only (no DB). start/stop block on subprocess calls.
"""
 
import subprocess
import threading
from dataclasses import dataclass
 
from flask import Flask, jsonify, request, abort
 
app = Flask(__name__)
 
# ---------------------------------------------------------------------------
# In-memory store (replace dict with something thread-safe if you ever add
# concurrent writers — a single RLock around all reads/writes is enough here)
# ---------------------------------------------------------------------------
 
@dataclass
class JobRecord:
    ejfat_uri_in: str
    ejfat_uri_out: str
    running: bool
 
_store: dict[str, JobRecord] = {}
_lock = threading.RLock()
 
 
# ---------------------------------------------------------------------------
# SLURM helpers  (fill in your actual sbatch/scancel invocations)
# ---------------------------------------------------------------------------
 
def _sbatch_start(nworkers: int) -> str:
    """Submit jobs, return the SLURM job ID string."""
    result = subprocess.run(
        ["sbatch", "--parsable", f"--export=ALL,N_WORKERS={nworkers}", "sink.sbatch"],
        capture_output=True, text=True, check=True,
    )
    slurm_job_id = result.stdout.strip()
 
    # TODO: submit worker array and source, thread slurm_job_id through as needed
    # For now we use the sink job ID as the canonical job_id returned to the caller.
    return slurm_job_id
 
 
def _sbatch_stop(job_id: str) -> None:
    """Cancel all jobs associated with this job_id."""
    subprocess.run(["scancel", job_id], check=True)
    # TODO: cancel worker array job ID if you're tracking it separately
 
 
def _derive_uris(job_id: str) -> tuple[str, str]:
    """
    Derive ejfat URIs for a freshly submitted job.
    Replace with however your system publishes these
    (e.g. read from a file the sink writes to shared FS).
    """
    ejfat_uri_in  = f"ejfat://<host>/<job_id>/{job_id}/in"   # placeholder
    ejfat_uri_out = f"ejfat://<host>/<job_id>/{job_id}/out"  # placeholder
    return ejfat_uri_in, ejfat_uri_out
 
 
# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
 
@app.post("/jobs")
def start():
    body = request.get_json(force=True, silent=True) or {}
    nworkers = body.get("nworkers")
    if not isinstance(nworkers, int) or nworkers < 1:
        abort(400, "nworkers must be a positive integer")
 
    job_id = _sbatch_start(nworkers)          # blocks until sbatch returns
    uri_in, uri_out = _derive_uris(job_id)
 
    with _lock:
        _store[job_id] = JobRecord(
            ejfat_uri_in=uri_in,
            ejfat_uri_out=uri_out,
            running=True,
        )
 
    return jsonify(job_id=job_id), 201
 
 
@app.delete("/jobs/<job_id>")
def stop(job_id: str):
    with _lock:
        record = _store.get(job_id)
        if record is None:
            abort(404, f"No job {job_id!r}")
        record.running = False               # mark before scancel returns
 
    _sbatch_stop(job_id)                     # blocks until scancel returns
 
    return jsonify({}), 200
 
 
@app.get("/jobs/<job_id>")
def status(job_id: str):
    with _lock:
        record = _store.get(job_id)
    if record is None:
        abort(404, f"No job {job_id!r}")
 
    return jsonify(
        ejfat_uri_in=record.ejfat_uri_in,
        ejfat_uri_out=record.ejfat_uri_out,
        running=record.running,
    ), 200


def add_arguments(parser):
    parser.add_argument("--port", type=int, default=8080, help="Port")

def run(args):
    print("Launching webserver")
    print("  port:  ", args.port)

    app.run(host="0.0.0.0", port=args.port, debug=True)
 
# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    # For production swap this for gunicorn (single worker to keep state coherent):
    #   gunicorn -w 1 api:app
    app.run(host="0.0.0.0", port=8080, debug=True)

