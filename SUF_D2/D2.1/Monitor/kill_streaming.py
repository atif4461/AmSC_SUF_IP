#!/usr/bin/env python3
"""Kill sender/receiver/launcher processes for this streaming demo."""

from __future__ import annotations

import argparse
import signal
import subprocess


def pids_matching(pattern: str) -> list[int]:
    res = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    if res.returncode not in (0, 1):
        return []
    pids = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def kill_pattern(pattern: str, sig: int) -> int:
    pids = pids_matching(pattern)
    if not pids:
        return 0
    killed = 0
    for pid in pids:
        try:
            subprocess.run(["kill", f"-{sig}", str(pid)], check=False)
            killed += 1
        except Exception:
            pass
    return killed


def main() -> None:
    parser = argparse.ArgumentParser(description="Kill sender/receiver/launcher processes")
    parser.add_argument("--force", action="store_true", help="Use SIGKILL directly")
    args = parser.parse_args()

    patterns = [
        r"[pP]ython(3)?\s+.*launch_senders\.py",
        r"[pP]ython(3)?\s+.*sender\.py",
        r"[pP]ython(3)?\s+.*receiver\.py",
    ]

    if args.force:
        sig = signal.SIGKILL
        total = sum(kill_pattern(p, sig) for p in patterns)
        print(f"Sent SIGKILL to {total} process(es).")
        return

    total_term = sum(kill_pattern(p, signal.SIGTERM) for p in patterns)
    print(f"Sent SIGTERM to {total_term} process(es).")

    # Ensure remaining are gone.
    total_kill = sum(kill_pattern(p, signal.SIGKILL) for p in patterns)
    if total_kill:
        print(f"Sent SIGKILL to {total_kill} stubborn process(es).")


if __name__ == "__main__":
    main()
