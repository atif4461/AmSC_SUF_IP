#!/usr/bin/env python3

import zmq
import signal
import sys

PULL_ADDRESS = "tcp://localhost:5555"
PUSH_ADDRESS = "tcp://localhost:5556"


def process_message(data: bytes) -> bytes:
    """
    Replace this with your real transformation logic.
    """
    # Example: uppercase transform
    print(f"Received {len(data)} bytes: {data!r}")
    return data.upper()

def main():
    context = zmq.Context.instance()

    pull_sock = context.socket(zmq.PULL)
    pull_sock.connect(PULL_ADDRESS)

    push_sock = context.socket(zmq.PUSH)
    push_sock.connect(PUSH_ADDRESS)

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutting down...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    poller = zmq.Poller()
    poller.register(pull_sock, zmq.POLLIN)

    print(f"Relaying {PULL_ADDRESS} → {PUSH_ADDRESS}")

    while running:
        events = dict(poller.poll(timeout=1000))  # 1s timeout

        if pull_sock in events:
            try:
                msg = pull_sock.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                continue

            result = process_message(msg)
            push_sock.send(result)

            print(f"Processed: {msg!r} -> {result!r}")

    pull_sock.close()
    push_sock.close()
    context.term()
    print("Exited cleanly.")


if __name__ == "__main__":
    main()

