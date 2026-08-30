#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

import httpx
from rich.live import Live
from rich.table import Table


def _stream_key(stream: dict) -> str:
    return f"{stream.get('sender_id', '')}|{stream.get('receiver_id', '')}"


def _compute_mbps(delta_bytes: int, delta_seconds: float) -> float:
    if delta_seconds <= 0:
        return 0.0
    return (float(delta_bytes) * 8.0) / (delta_seconds * 1_000_000.0)


def _build_rate_map(metrics: dict, prev_bytes: dict[str, tuple[int, int]], delta_seconds: float) -> dict[str, tuple[float, float]]:
    rates: dict[str, tuple[float, float]] = {}
    for stream in metrics.get("streams", []):
        key = _stream_key(stream)
        tx_bytes = int(stream.get("tx_bytes", 0))
        rx_bytes = int(stream.get("rx_bytes", 0))
        prev_tx, prev_rx = prev_bytes.get(key, (tx_bytes, rx_bytes))

        delta_tx = max(0, tx_bytes - prev_tx)
        delta_rx = max(0, rx_bytes - prev_rx)
        rates[key] = (
            _compute_mbps(delta_tx, delta_seconds),
            _compute_mbps(delta_rx, delta_seconds),
        )
    return rates


def _build_worker_rate_map(
    metrics: dict,
    prev_bytes: dict[int, tuple[int, int]],
    delta_seconds: float,
) -> dict[int, tuple[float, float]]:
    rates: dict[int, tuple[float, float]] = {}
    workers = metrics.get("workers")
    if not isinstance(workers, list):
        return rates

    for worker in workers:
        wid = int(worker.get("worker_id", -1))
        if wid < 0:
            continue
        rx_bytes = int(worker.get("rx_datagram_bytes", 0))
        fwd_bytes = int(worker.get("forwarded_bytes", 0))
        prev_rx, prev_fwd = prev_bytes.get(wid, (rx_bytes, fwd_bytes))
        delta_rx = max(0, rx_bytes - prev_rx)
        delta_fwd = max(0, fwd_bytes - prev_fwd)
        rates[wid] = (
            _compute_mbps(delta_rx, delta_seconds),
            _compute_mbps(delta_fwd, delta_seconds),
        )

    return rates


def render(
    metrics: dict,
    rates: dict[str, tuple[float, float]],
    worker_rates: dict[int, tuple[float, float]],
) -> Table:
    table = Table(title=f"EJFAT Emulator Metrics | lb_id={metrics.get('lb_id', 'unknown')}")
    table.add_column("Sender")
    table.add_column("Receiver")
    table.add_column("Tx Pkts", justify="right")
    table.add_column("Rx Pkts", justify="right")
    table.add_column("Loss %", justify="right")
    table.add_column("Tx Mbps", justify="right")
    table.add_column("Rx Mbps", justify="right")
    table.add_column("Tx Bytes", justify="right")
    table.add_column("Rx Bytes", justify="right")

    for stream in metrics.get("streams", []):
        key = _stream_key(stream)
        tx_mbps, rx_mbps = rates.get(key, (0.0, 0.0))
        table.add_row(
            str(stream.get("sender_id", "")),
            str(stream.get("receiver_id", "")),
            str(stream.get("tx_packets", 0)),
            str(stream.get("rx_packets", 0)),
            f"{stream.get('packet_loss_pct', 0.0):.3f}",
            f"{tx_mbps:.2f}",
            f"{rx_mbps:.2f}",
            str(stream.get("tx_bytes", 0)),
            str(stream.get("rx_bytes", 0)),
        )

    workers = metrics.get("workers")
    if isinstance(workers, list) and workers:
        table.add_section()
        for worker in workers:
            wid = worker.get("worker_id", "?")
            rx = worker.get("rx_datagrams", 0)
            fwd = worker.get("forwarded", 0)
            drp = worker.get("dropped", 0)
            err = worker.get("send_errors", 0)
            rx_bytes = worker.get("rx_datagram_bytes", 0)
            fwd_bytes = worker.get("forwarded_bytes", 0)
            ingress_mbps, egress_mbps = worker_rates.get(int(wid), (0.0, 0.0)) if str(wid).isdigit() else (0.0, 0.0)
            table.add_row(
                f"worker-{wid}",
                "(summary)",
                str(rx),
                str(fwd),
                "-",
                f"{ingress_mbps:.2f}",
                f"{egress_mbps:.2f}",
                str(rx_bytes),
                str(fwd_bytes),
            )
    return table


def run(args: argparse.Namespace) -> None:
    headers = {"Authorization": args.auth}
    url = f"{args.api_base}/movement/streaming/ejfat/control-plane-ip/loadbalancers/{args.lb_id}/metrics"
    with httpx.Client(timeout=2.0, headers=headers) as client:
        with Live(refresh_per_second=4) as live:
            end = time.time() + args.duration if args.duration > 0 else None
            prev_time = time.time()
            prev_bytes: dict[str, tuple[int, int]] = {}
            prev_worker_bytes: dict[int, tuple[int, int]] = {}
            while True:
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    metrics = resp.json()

                    now = time.time()
                    delta_seconds = max(0.001, now - prev_time)
                    rates = _build_rate_map(metrics, prev_bytes, delta_seconds)
                    worker_rates = _build_worker_rate_map(metrics, prev_worker_bytes, delta_seconds)

                    current_bytes: dict[str, tuple[int, int]] = {}
                    for stream in metrics.get("streams", []):
                        key = _stream_key(stream)
                        current_bytes[key] = (
                            int(stream.get("tx_bytes", 0)),
                            int(stream.get("rx_bytes", 0)),
                        )

                    current_worker_bytes: dict[int, tuple[int, int]] = {}
                    workers = metrics.get("workers")
                    if isinstance(workers, list):
                        for worker in workers:
                            wid = int(worker.get("worker_id", -1))
                            if wid < 0:
                                continue
                            current_worker_bytes[wid] = (
                                int(worker.get("rx_datagram_bytes", 0)),
                                int(worker.get("forwarded_bytes", 0)),
                            )

                    prev_bytes = current_bytes
                    prev_worker_bytes = current_worker_bytes
                    prev_time = now
                    live.update(render(metrics, rates, worker_rates))
                except Exception as exc:
                    err = Table(title="EJFAT Emulator Metrics")
                    err.add_column("Error")
                    err.add_row(str(exc))
                    live.update(err)

                if end is not None and time.time() >= end:
                    break
                time.sleep(args.interval)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TUI monitor for EJFAT emulator metrics")
    p.add_argument("--api-base", default="http://127.0.0.1:18080")
    p.add_argument("--lb-id", required=True)
    p.add_argument("--auth", default="Bearer local-dev")
    p.add_argument("--interval", type=float, default=0.5)
    p.add_argument("--duration", type=float, default=20.0, help="0 for infinite")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
