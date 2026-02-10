#!/usr/bin/env python3

import zmq
import time
import signal
import sys

ADDRESS = "tcp://*:5555"
INTERVAL = 1.0  # seconds


def make_message(counter: int) -> bytes:
    """
    Replace this with your real data production logic.
    """
    payload = f"message #{counter} @ {time.time():.3f}"
    return payload.encode("utf-8")


def main():
    context = zmq.Context.instance()
    socket = context.socket(zmq.PUSH)
    socket.bind(ADDRESS)

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutting down...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Connected to {ADDRESS}")

    counter = 0
    next_send = time.monotonic()

    while running:
        now = time.monotonic()

        if now >= next_send:
            msg = make_message(counter)
            socket.send(msg)
            print(f"Sent: {msg!r}")

            counter += 1
            next_send += INTERVAL

        # Sleep just enough to avoid busy-waiting
        time.sleep(min(0.1, max(0.0, next_send - time.monotonic())))

    socket.close()
    context.term()
    print("Exited cleanly.")


if __name__ == "__main__":
    main()



