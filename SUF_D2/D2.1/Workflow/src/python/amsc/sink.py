
import argparse
import zmq
import signal
import sys
import socket
import time

from amsc import credentials,ejfat

def add_arguments(parser):
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--stats-every", type=int, default=100, help="Print one stats line every N forwarded messages")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")


def process_data(data: bytes, verbose) -> bytes:
    # Keep data in Arrow/bytes form for efficiency.
    # Worker already produced reduced tables needed downstream.
    if verbose:
        print(f"Forwarding {len(data)} bytes to processed EJFAT stream")
    return data


def run(args):

    print("Running sink:")
    print("    credential_dir: ", args.credential_dir)
    print("    stats_every:    ", args.stats_every)
    print("    verbose:        ", args.verbose)
    print()

    # Fire up ZMQ
    context = zmq.Context.instance()
    socket = context.socket(zmq.PULL)
    socket.bind("tcp://0.0.0.0:5555")

    # We want to bind the socket _before_ we notify the workers
    zmq_uri_sink = credentials.put_zmq_address(args.credential_dir)
    print("Bound ZMQ socket: ", zmq_uri_sink)

    # Fire up EJFAT
    ejfat_uri_processed = credentials.get_ejfat_uri_processed(args.credential_dir)
    ejfat_sender = ejfat.EjfatSender(ejfat_uri_processed)
    ejfat_sender.connect()
    print("Connected to EJFAT: ", ejfat_uri_processed)
    print()

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    forwarded_count = 0
    dropped_count = 0
    t0 = time.monotonic()
    stats_every = max(1, int(args.stats_every))


    while running:
        if args.verbose:
            print("Sink: Waiting for incoming events...")
        events = dict(poller.poll(timeout=1000))  # 1s timeout

        if socket in events:
            try:
                if args.verbose:
                    print("Found socket in events")
                msg = socket.recv(flags=zmq.NOBLOCK)
                result = process_data(msg, args.verbose) # Returns bytes
                ejfat_sender.send(result)
                forwarded_count += 1
                if forwarded_count % stats_every == 0:
                    dt = max(1e-9, time.monotonic() - t0)
                    rate = forwarded_count / dt
                    print(
                        f"sink forwarded={forwarded_count} dropped={dropped_count} "
                        f"rate={rate:.1f} msg/s"
                    )

            except zmq.Again:
                # No message available (race with poll)
                continue
            except Exception as exc:
                dropped_count += 1
                print(f"Warning: failed to forward message ({dropped_count} drops): {exc}")

    socket.close()
    context.term()

    ejfat_sender.disconnect()

    print("Exited cleanly.")



