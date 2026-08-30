#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


@dataclass
class SweepRow:
    workers: int
    senders: int
    rate_per_sender_pps: int
    payload_bytes: int
    offered_mbps: float
    tx_packets: int
    rx_packets: int
    dropped_packets: int
    loss_pct: float
    worker_rx_datagrams: int
    worker_forwarded: int
    worker_dropped: int


def delivered_goodput_mbps(row: SweepRow) -> float:
    if row.tx_packets <= 0:
        return 0.0
    delivered_ratio = row.rx_packets / row.tx_packets
    return row.offered_mbps * max(0.0, min(1.0, delivered_ratio))


def detect_knees(rows: list[SweepRow], threshold_pct: float) -> dict[int, SweepRow]:
    knees: dict[int, SweepRow] = {}
    by_workers: dict[int, list[SweepRow]] = {}
    for row in rows:
        by_workers.setdefault(row.workers, []).append(row)

    for workers, grp in by_workers.items():
        grp_sorted = sorted(grp, key=lambda r: r.offered_mbps)
        for row in grp_sorted:
            if row.loss_pct >= threshold_pct:
                knees[workers] = row
                break
    return knees


def parse_csv_ints(value: str) -> list[int]:
    values: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    if not values:
        raise argparse.ArgumentTypeError("Expected at least one integer")
    return values


def wait_for_health(api_base: str, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    last_error = "health timeout"
    with httpx.Client(timeout=1.5) as client:
        while time.time() < deadline:
            try:
                r = client.get(f"{api_base}/health")
                if r.status_code == 200:
                    return
                last_error = f"health returned {r.status_code}"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"Emulator did not become healthy: {last_error}")


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def parse_api_host_port(api_base: str) -> tuple[str, int]:
    parsed = urlparse(api_base)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported API base scheme: {api_base}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return host, port


def start_emulator(workers: int, flush_ms: int, pin_workers: bool, log_file: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = env.get("PYTHONPATH", "src")
    env["EJFAT_DATA_WORKERS"] = str(workers)
    env["EJFAT_METRICS_FLUSH_INTERVAL_MS"] = str(flush_ms)
    env["EJFAT_PIN_WORKERS"] = "true" if pin_workers else "false"

    log_file.parent.mkdir(parents=True, exist_ok=True)
    f = log_file.open("w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", "ejfat_emulator.main"],
        env=env,
        stdout=f,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def stop_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=5)


def create_reservation(client: httpx.Client, api_base: str, auth: str, name: str) -> dict[str, Any]:
    payload = {
        "name": name,
        "sender_addresses": ["127.0.0.1"],
        "ip_family": "dual_stack",
        "strategy": "dynamic",
    }
    r = client.post(
        f"{api_base}/movement/streaming/ejfat/control-plane-ip/loadbalancers",
        headers={"Authorization": auth},
        json=payload,
    )
    r.raise_for_status()
    return r.json()


def delete_reservation(client: httpx.Client, api_base: str, auth: str, lb_id: str) -> None:
    _ = client.delete(
        f"{api_base}/movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}",
        headers={"Authorization": auth},
        timeout=3.0,
    )


def run_receiver(host: str, data_port: int, lb_id: str, token: str, duration: int) -> subprocess.Popen[str]:
    log_path = Path("artifacts/logs") / f"receiver_{lb_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "tools/receiver.py",
            "--host",
            host,
            "--data-port",
            str(data_port),
            "--listen-port",
            "18100",
            "--lb-id",
            lb_id,
            "--token",
            token,
            "--receiver-id",
            "receiver-1",
            "--duration",
            str(duration),
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )


def run_sender(
    host: str,
    data_port: int,
    lb_id: str,
    token: str,
    sender_id: str,
    rate: int,
    count: int,
    payload_bytes: int,
) -> subprocess.Popen[str]:
    log_path = Path("artifacts/logs") / f"sender_{lb_id}_{sender_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "tools/sender.py",
            "--host",
            host,
            "--data-port",
            str(data_port),
            "--lb-id",
            lb_id,
            "--token",
            token,
            "--sender-id",
            sender_id,
            "--receiver-id",
            "receiver-1",
            "--rate",
            str(rate),
            "--count",
            str(count),
            "--payload-bytes",
            str(payload_bytes),
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )


def fetch_metrics(client: httpx.Client, api_base: str, auth: str, lb_id: str) -> dict[str, Any]:
    r = client.get(
        f"{api_base}/movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}/metrics",
        headers={"Authorization": auth},
    )
    r.raise_for_status()
    return r.json()


def fetch_metrics_with_retry(
    client: httpx.Client,
    api_base: str,
    auth: str,
    lb_id: str,
    retries: int = 10,
    sleep_s: float = 0.25,
) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for _ in range(retries):
        latest = fetch_metrics(client, api_base, auth, lb_id)
        streams = latest.get("streams", [])
        tx_packets = sum(int(s.get("tx_packets", 0)) for s in streams)
        if tx_packets > 0:
            return latest
        time.sleep(sleep_s)
    return latest


def build_row(
    metrics: dict[str, Any],
    workers: int,
    senders: int,
    rate: int,
    payload_bytes: int,
) -> SweepRow:
    streams = metrics.get("streams", [])
    workers_metrics = metrics.get("workers", [])

    tx_packets = sum(int(s.get("tx_packets", 0)) for s in streams)
    rx_packets = sum(int(s.get("rx_packets", 0)) for s in streams)
    dropped_packets = sum(int(s.get("dropped_packets", 0)) for s in streams)
    loss_pct = 0.0
    if tx_packets > 0:
        loss_pct = ((tx_packets - rx_packets) / tx_packets) * 100.0

    worker_rx_datagrams = sum(int(w.get("rx_datagrams", 0)) for w in workers_metrics)
    worker_forwarded = sum(int(w.get("forwarded", 0)) for w in workers_metrics)
    worker_dropped = sum(int(w.get("dropped", 0)) for w in workers_metrics)

    offered_mbps = (senders * rate * payload_bytes * 8.0) / 1_000_000.0

    return SweepRow(
        workers=workers,
        senders=senders,
        rate_per_sender_pps=rate,
        payload_bytes=payload_bytes,
        offered_mbps=offered_mbps,
        tx_packets=tx_packets,
        rx_packets=rx_packets,
        dropped_packets=dropped_packets,
        loss_pct=max(loss_pct, 0.0),
        worker_rx_datagrams=worker_rx_datagrams,
        worker_forwarded=worker_forwarded,
        worker_dropped=worker_dropped,
    )


def write_csv(rows: list[SweepRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "workers",
                "senders",
                "rate_per_sender_pps",
                "payload_bytes",
                "offered_mbps",
                "tx_packets",
                "rx_packets",
                "dropped_packets",
                "loss_pct",
                "worker_rx_datagrams",
                "worker_forwarded",
                "worker_dropped",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def write_plot(rows: list[SweepRow], path: Path, knee_threshold_pct: float) -> bool:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return False

    by_workers: dict[int, list[SweepRow]] = {}
    for row in rows:
        by_workers.setdefault(row.workers, []).append(row)
    knees = detect_knees(rows, knee_threshold_pct)

    plt.figure(figsize=(10, 6))
    for workers, grp in sorted(by_workers.items()):
        grp_sorted = sorted(grp, key=lambda r: r.offered_mbps)
        x = [r.offered_mbps for r in grp_sorted]
        y = [r.loss_pct for r in grp_sorted]
        plt.plot(x, y, marker="o", linewidth=2, label=f"workers={workers}")

        knee = knees.get(workers)
        if knee is not None:
            plt.scatter([knee.offered_mbps], [knee.loss_pct], s=90, marker="X", zorder=5)
            plt.annotate(
                f"knee w={workers}\n{knee.offered_mbps:.1f} Mbps",
                (knee.offered_mbps, knee.loss_pct),
                textcoords="offset points",
                xytext=(6, 8),
                fontsize=8,
            )

    plt.xlabel("Offered Load (Mbps)")
    plt.ylabel("Loss (%)")
    plt.title("EJFAT Emulator Stress Sweep")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=140)
    plt.close()
    return True


def write_goodput_plot(rows: list[SweepRow], path: Path, knee_threshold_pct: float) -> bool:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return False

    by_workers: dict[int, list[SweepRow]] = {}
    for row in rows:
        by_workers.setdefault(row.workers, []).append(row)
    knees = detect_knees(rows, knee_threshold_pct)

    plt.figure(figsize=(10, 6))
    for workers, grp in sorted(by_workers.items()):
        grp_sorted = sorted(grp, key=lambda r: r.offered_mbps)
        x = [r.offered_mbps for r in grp_sorted]
        y = [delivered_goodput_mbps(r) for r in grp_sorted]
        plt.plot(x, y, marker="o", linewidth=2, label=f"workers={workers}")

        knee = knees.get(workers)
        if knee is not None:
            knee_goodput = delivered_goodput_mbps(knee)
            plt.scatter([knee.offered_mbps], [knee_goodput], s=90, marker="X", zorder=5)
            plt.annotate(
                f"knee w={workers}",
                (knee.offered_mbps, knee_goodput),
                textcoords="offset points",
                xytext=(6, 8),
                fontsize=8,
            )

    diagonal_max = max((r.offered_mbps for r in rows), default=1.0)
    plt.plot([0.0, diagonal_max], [0.0, diagonal_max], linestyle="--", linewidth=1.5, color="gray", alpha=0.7, label="ideal y=x")

    plt.xlabel("Offered Load (Mbps)")
    plt.ylabel("Delivered Goodput (Mbps)")
    plt.title("EJFAT Emulator Throughput Curve")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=140)
    plt.close()
    return True


def write_combined_plot(rows: list[SweepRow], path: Path, knee_threshold_pct: float) -> bool:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return False

    by_workers: dict[int, list[SweepRow]] = {}
    for row in rows:
        by_workers.setdefault(row.workers, []).append(row)
    knees = detect_knees(rows, knee_threshold_pct)

    fig, ax_loss = plt.subplots(figsize=(11, 6.5))
    ax_goodput = ax_loss.twinx()

    for workers, grp in sorted(by_workers.items()):
        grp_sorted = sorted(grp, key=lambda r: r.offered_mbps)
        x = [r.offered_mbps for r in grp_sorted]
        loss_y = [r.loss_pct for r in grp_sorted]
        goodput_y = [delivered_goodput_mbps(r) for r in grp_sorted]

        ax_loss.plot(x, loss_y, marker="o", linewidth=2, label=f"loss w={workers}")
        ax_goodput.plot(x, goodput_y, marker="s", linestyle="--", linewidth=2, label=f"goodput w={workers}")

        knee = knees.get(workers)
        if knee is not None:
            knee_goodput = delivered_goodput_mbps(knee)
            ax_loss.scatter([knee.offered_mbps], [knee.loss_pct], s=90, marker="X", zorder=6)
            ax_goodput.scatter([knee.offered_mbps], [knee_goodput], s=70, marker="D", zorder=6)
            ax_loss.annotate(
                f"knee w={workers}",
                (knee.offered_mbps, knee.loss_pct),
                textcoords="offset points",
                xytext=(6, 8),
                fontsize=8,
            )

    diagonal_max = max((r.offered_mbps for r in rows), default=1.0)
    ax_goodput.plot(
        [0.0, diagonal_max],
        [0.0, diagonal_max],
        linestyle=":",
        linewidth=1.5,
        color="gray",
        alpha=0.7,
        label="ideal goodput",
    )

    ax_loss.set_xlabel("Offered Load (Mbps)")
    ax_loss.set_ylabel("Loss (%)")
    ax_goodput.set_ylabel("Delivered Goodput (Mbps)")
    ax_loss.set_title("EJFAT Combined Stress View: Loss and Goodput")
    ax_loss.grid(True, linestyle="--", alpha=0.4)

    loss_handles, loss_labels = ax_loss.get_legend_handles_labels()
    gp_handles, gp_labels = ax_goodput.get_legend_handles_labels()
    ax_loss.legend(loss_handles + gp_handles, loss_labels + gp_labels, loc="best", fontsize=9)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run stress sweep across worker counts and sender rates.")
    parser.add_argument("--workers", type=parse_csv_ints, default=[1, 2, 4, 8])
    parser.add_argument("--rates", type=parse_csv_ints, default=[2000, 5000, 10000, 20000])
    parser.add_argument("--senders", type=int, default=8)
    parser.add_argument("--count-per-sender", type=int, default=20000)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--api-base", default="http://127.0.0.1:18080")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--data-port", type=int, default=18020)
    parser.add_argument("--auth", default="Bearer local-dev")
    parser.add_argument("--flush-ms", type=int, default=50)
    parser.add_argument("--pin-workers", action="store_true")
    parser.add_argument("--knee-loss-threshold", type=float, default=1.0)
    parser.add_argument("--output-csv", default="artifacts/stress_sweep.csv")
    parser.add_argument("--output-plot", default="artifacts/stress_sweep.png")
    parser.add_argument("--output-goodput-plot", default="artifacts/stress_sweep_goodput.png")
    parser.add_argument("--output-combined-plot", default="artifacts/stress_sweep_combined.png")
    parser.add_argument("--output-json", default="artifacts/stress_sweep.json")
    parser.add_argument("--output-knees-json", default="artifacts/stress_sweep_knees.json")
    args = parser.parse_args()

    api_host, api_port = parse_api_host_port(args.api_base)

    rows: list[SweepRow] = []

    for workers in args.workers:
        if is_port_in_use(api_host, api_port):
            raise RuntimeError(
                f"API port already in use at {api_host}:{api_port}. "
                "Stop existing emulator/server before running stress sweep."
            )

        emu_log = Path(f"artifacts/logs/emulator_w{workers}.log")
        print(f"[sweep] starting emulator workers={workers}")
        proc = start_emulator(workers, args.flush_ms, args.pin_workers, emu_log)
        try:
            wait_for_health(args.api_base, timeout_s=20.0)
            if proc.poll() is not None:
                raise RuntimeError(
                    f"Emulator exited early with code {proc.returncode}; see {emu_log}"
                )
        except Exception as exc:  # noqa: BLE001
            stop_process_tree(proc)
            raise RuntimeError(f"Emulator failed to start for workers={workers}: {exc}") from exc

        with httpx.Client(timeout=30.0) as client:
            for rate in args.rates:
                print(f"[sweep] workers={workers} rate_per_sender={rate}")
                reservation = create_reservation(
                    client,
                    args.api_base,
                    args.auth,
                    f"stress-w{workers}-r{rate}",
                )
                lb_id = str(reservation["lb_id"])
                token = str(reservation["token"])

                trial_duration = max(args.duration, int((args.count_per_sender / max(rate, 1)) + 6))
                rx_proc = run_receiver(args.host, args.data_port, lb_id, token, trial_duration)
                time.sleep(1.0)

                sender_procs = [
                    run_sender(
                        args.host,
                        args.data_port,
                        lb_id,
                        token,
                        f"sender-{idx + 1}",
                        rate,
                        args.count_per_sender,
                        args.payload_bytes,
                    )
                    for idx in range(args.senders)
                ]

                for sender in sender_procs:
                    sender.wait(timeout=trial_duration + 30)
                    if sender.returncode != 0:
                        raise RuntimeError(f"Sender exited with code {sender.returncode} for lb_id={lb_id}")

                rx_proc.wait(timeout=trial_duration + 20)
                if rx_proc.returncode != 0:
                    raise RuntimeError(f"Receiver exited with code {rx_proc.returncode} for lb_id={lb_id}")

                metrics = fetch_metrics_with_retry(client, args.api_base, args.auth, lb_id)
                row = build_row(metrics, workers, args.senders, rate, args.payload_bytes)
                rows.append(row)
                delete_reservation(client, args.api_base, args.auth, lb_id)

                print(
                    "[sweep] result"
                    f" workers={workers} offered_mbps={row.offered_mbps:.2f}"
                    f" tx={row.tx_packets} rx={row.rx_packets}"
                    f" loss_pct={row.loss_pct:.3f}"
                )

        stop_process_tree(proc)
        time.sleep(0.5)

    output_csv = Path(args.output_csv)
    output_json = Path(args.output_json)
    output_plot = Path(args.output_plot)
    output_goodput_plot = Path(args.output_goodput_plot)
    output_combined_plot = Path(args.output_combined_plot)
    output_knees_json = Path(args.output_knees_json)

    write_csv(rows, output_csv)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps([row.__dict__ for row in rows], indent=2),
        encoding="utf-8",
    )

    plotted = write_plot(rows, output_plot, args.knee_loss_threshold)
    goodput_plotted = write_goodput_plot(rows, output_goodput_plot, args.knee_loss_threshold)
    combined_plotted = write_combined_plot(rows, output_combined_plot, args.knee_loss_threshold)

    knees = detect_knees(rows, args.knee_loss_threshold)
    knees_payload = {
        "knee_loss_threshold_pct": args.knee_loss_threshold,
        "knees": {
            str(workers): {
                "workers": row.workers,
                "offered_mbps": row.offered_mbps,
                "loss_pct": row.loss_pct,
                "delivered_goodput_mbps": delivered_goodput_mbps(row),
                "tx_packets": row.tx_packets,
                "rx_packets": row.rx_packets,
            }
            for workers, row in sorted(knees.items())
        },
        "workers_without_knee": sorted(list({row.workers for row in rows} - set(knees.keys()))),
    }
    output_knees_json.parent.mkdir(parents=True, exist_ok=True)
    output_knees_json.write_text(json.dumps(knees_payload, indent=2), encoding="utf-8")

    print(f"[sweep] wrote {output_csv}")
    print(f"[sweep] wrote {output_json}")
    print(f"[sweep] wrote {output_knees_json}")
    if plotted:
        print(f"[sweep] wrote {output_plot}")
    else:
        print("[sweep] matplotlib not available; CSV/JSON generated but plot skipped.")
        print("[sweep] install matplotlib in your venv to enable PNG plot output.")

    if goodput_plotted:
        print(f"[sweep] wrote {output_goodput_plot}")
    elif plotted:
        print("[sweep] matplotlib available but failed to write goodput plot.")

    if combined_plotted:
        print(f"[sweep] wrote {output_combined_plot}")
    elif plotted:
        print("[sweep] matplotlib available but failed to write combined dual-axis plot.")

    for workers in sorted({row.workers for row in rows}):
        knee = knees.get(workers)
        if knee is None:
            print(
                f"[sweep] knee workers={workers}: not reached (loss < {args.knee_loss_threshold:.3f}% in tested range)"
            )
        else:
            print(
                f"[sweep] knee workers={workers}: offered={knee.offered_mbps:.2f} Mbps "
                f"loss={knee.loss_pct:.3f}% goodput={delivered_goodput_mbps(knee):.2f} Mbps"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
