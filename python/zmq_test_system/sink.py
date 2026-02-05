#!/usr/bin/env python3

import zmq
import signal
import sys

ADDRESS = "tcp://*:5556"


def process_message(data: bytes) -> None:
    """
    Replace this with your real processing logic.
    """
    print(f"Received {len(data)} bytes: {data!r}")


def main():
    context = zmq.Context.instance()
    socket = context.socket(zmq.PULL)
    socket.bind(ADDRESS)

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutting down...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Listening on {ADDRESS}")

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    while running:
        events = dict(poller.poll(timeout=1000))  # 1s timeout

        if socket in events:
            try:
                msg = socket.recv(flags=zmq.NOBLOCK)
                process_message(msg)
            except zmq.Again:
                # No message available (race with poll)
                continue

    socket.close()
    context.term()
    print("Exited cleanly.")


if __name__ == "__main__":
    main()

