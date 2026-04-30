#!/usr/bin/env python3
"""Launch multiple sender processes and block until interrupted."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path


def terminate_children(children: list[subprocess.Popen]) -> None:
    for p in children:
        if p.poll() is None:
            p.terminate()
    deadline = time.time() + 3.0
    for p in children:
        if p.poll() is not None:
            continue
        remain = max(0.0, deadline - time.time())
        try:
            p.wait(timeout=remain)
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch multiple sender.py processes")
    parser.add_argument("--num", type=int, required=True, help="Number of senders to launch")
    parser.add_argument("--chunks-per-second", type=float, default=6.0, help="Rate per sender")
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5557", help="Receiver endpoint")
    parser.add_argument("--input", default="data/first_10_events.pickle", help="Seed pickle path")
    parser.add_argument("--seed-base", type=int, default=1000, help="Base RNG seed; sender i uses seed_base+i")
    args = parser.parse_args()

    if args.num <= 0:
        raise ValueError("--num must be > 0")

    root = Path(__file__).resolve().parent
    sender_path = root / "sender.py"

    children: list[subprocess.Popen] = []
    stopping = False

    def _handle_signal(signum, frame) -> None:  # type: ignore[no-untyped-def]
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print("\nStopping launched senders...")
        terminate_children(children)
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    for i in range(args.num):
        seed = args.seed_base + i
        cmd = [
            sys.executable,
            str(sender_path),
            "--input",
            args.input,
            "--endpoint",
            args.endpoint,
            "--chunks-per-second",
            str(args.chunks_per_second),
            "--seed",
            str(seed),
        ]
        p = subprocess.Popen(cmd, cwd=str(root))
        children.append(p)
        print(f"Launched sender {i + 1}/{args.num} (pid={p.pid}, seed={seed})")

    print("Launcher running. Press Ctrl-C to stop all launched senders.")
    try:
        while True:
            # If any sender exits unexpectedly, keep running others.
            time.sleep(0.5)
    except KeyboardInterrupt:
        _handle_signal(signal.SIGINT, None)


if __name__ == "__main__":
    main()
