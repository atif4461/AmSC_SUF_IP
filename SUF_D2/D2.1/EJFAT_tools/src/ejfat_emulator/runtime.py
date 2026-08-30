from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


STATE_DIR = Path(os.getenv("EJFAT_STATE_DIR", "/tmp/ejfat-emulator"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

_REPO_ROOT = Path(__file__).resolve().parents[2]

RESERVATIONS_FILE = STATE_DIR / "reservations.json"
METRICS_FILE = STATE_DIR / "metrics.json"

_DATA_PORT = int(os.getenv("EJFAT_DATA_PORT", "18020"))
_DROP_RATE = float(os.getenv("EJFAT_EMULATED_DROP_RATE", "0.0"))
_WORKERS = int(os.getenv("EJFAT_DATA_WORKERS", "2"))
_FLUSH_INTERVAL_MS = int(os.getenv("EJFAT_METRICS_FLUSH_INTERVAL_MS", "100"))
_PIN_WORKERS = os.getenv("EJFAT_PIN_WORKERS", "false").lower() in {"1", "true", "yes", "on"}
_PIN_BASE_CPU = int(os.getenv("EJFAT_PIN_BASE_CPU", "0"))


class LBProcessManager:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def ensure_started(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return

            RESERVATIONS_FILE.write_text("[]\n")
            METRICS_FILE.write_text("{}\n")

            candidates = [
                _REPO_ROOT / "bin" / "lb_dataplane",
                Path("/app/bin/lb_dataplane"),
            ]
            binary = None
            for c in candidates:
                if c.exists() and os.access(c, os.X_OK):
                    binary = c
                    break
            if binary is None:
                raise RuntimeError("C++ data-plane binary not found. Build it with scripts/build_cpp_lb.sh")

            cmd = [
                str(binary),
                "--data-port",
                str(_DATA_PORT),
                "--reservations-file",
                str(RESERVATIONS_FILE),
                "--metrics-file",
                str(METRICS_FILE),
                "--drop-rate",
                str(_DROP_RATE),
                "--workers",
                str(max(1, _WORKERS)),
                "--flush-interval-ms",
                str(max(10, _FLUSH_INTERVAL_MS)),
                "--pin-workers",
                "true" if _PIN_WORKERS else "false",
                "--pin-base-cpu",
                str(max(0, _PIN_BASE_CPU)),
            ]
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)

            deadline = time.time() + 2.0
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    raise RuntimeError("C++ data-plane failed to start")
                if METRICS_FILE.exists():
                    return
                time.sleep(0.05)

            raise RuntimeError("Timed out waiting for C++ data-plane startup")

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except Exception:
                    self._proc.kill()
            self._proc = None


class SharedState:
    @staticmethod
    def write_reservations(reservations: list[dict[str, Any]]) -> None:
        RESERVATIONS_FILE.write_text(json.dumps(reservations) + "\n")

    @staticmethod
    def read_metrics() -> dict[str, Any]:
        if not METRICS_FILE.exists():
            return {}
        try:
            raw = METRICS_FILE.read_text()
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {}
            return data
        except Exception:
            return {}


lb_process_manager = LBProcessManager()
