
import argparse
import zmq
import signal
import sys
import socket
import time

from amsc import credentials,ejfat

def add_arguments(parser):
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--stats-every", type=float, default=1.0, help="Print one stats line every n seconds")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")
    parser.add_argument("--mtu", type=int, default=1500, help="EJFAT max transmission unit")
    parser.add_argument("--ip", type=str, default=None, help="IP address to register with LB (defaults to autoip)")
    parser.add_argument("--zmq-port", type=int, default=5555, help="TCP port for worker results")

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
    print("    mtu:            ", args.mtu)
    print("    ip:             ", args.ip)
    print("    verbose:        ", args.verbose)
    print("    zmq_port:       ", args.zmq_port)
    print()


    if not 1 <= args.zmq_port <= 65535:
        raise ValueError("--zmq-port must be between 1 and 65535")

    # Fire up ZMQ
    context = zmq.Context.instance()
    socket = context.socket(zmq.PULL)
    bind_uri = f"tcp://0.0.0.0:{args.zmq_port}"
    socket.bind(bind_uri)

    # We want to bind the socket _before_ we notify the workers
    zmq_uri_sink = credentials.put_zmq_address(args.credential_dir, port=args.zmq_port)
    print("Bound ZMQ socket: ", bind_uri)
    print("Advertised ZMQ endpoint: ", zmq_uri_sink)

    # Fire up EJFAT
    ejfat_uri_processed = credentials.get_ejfat_uri_processed(args.credential_dir)
    ejfat_sender = ejfat.EjfatSender(ejfat_uri_processed, 0, args.mtu, args.ip)
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

    while running:
        if args.verbose:
            print("Sink: Waiting for incoming events...")
        events = dict(poller.poll(timeout=100))  # .1s timeout

        if socket in events:
            try:
                if args.verbose:
                    print("Found socket in events")
                msg = socket.recv(flags=zmq.NOBLOCK)
                result = process_data(msg, args.verbose) # Returns bytes
                ejfat_sender.send(result)
                forwarded_count += 1

            except zmq.Again:
                # No message available (race with poll)
                continue
            except Exception as exc:
                dropped_count += 1
                print(f"Warning: failed to forward message ({dropped_count} drops): {exc}")

        t1 = time.monotonic()
        if (t1-t0) > args.stats_every:
            rate = forwarded_count / (t1-t0)
            print(
                f"sink forwarded={forwarded_count} dropped={dropped_count} "
                f"rate={rate:.1f} msg/s"
            )
            t0 = t1
            forwarded_count = 0
            dropped_count = 0

    socket.close()
    context.term()

    ejfat_sender.disconnect()

    print("Exited cleanly.")



