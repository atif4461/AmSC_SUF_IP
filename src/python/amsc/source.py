
import argparse
import zmq
import time
import signal
import sys
import pandas

from . import hddm_reader

ADDRESS = "tcp://*:5555"


def make_fake_data(counter: int) -> bytes:
    # Fake data goes here


    payload = f"message #{counter} @ {time.time():.3f}"
    return payload.encode("utf-8")

def add_arguments(parser):
    parser.add_argument("input_filename", help="Input REST filename")
    parser.add_argument("--name", default="source0", help="Name for this source")
    parser.add_argument("--address", default=ADDRESS, help="Address of load balancer or ZMQ socket")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval [s] between sends")
    parser.add_argument("--ejfat", action=argparse.BooleanOptionalAction, default=False, help="Stream over EJFAT load balancer")
    parser.add_argument("--batch-size", type=int, default=1, help="Physics events per message")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True, help="Loop input file for infinite stream")


def run(args):
    print("Running source:")
    print("  input_filename:", args.input_filename)
    print("  name:          ", args.name)
    print("  address:       ", args.address)
    print("  use_ejfat:     ", args.ejfat)
    print("  batch_size:    ", args.batch_size)
    print("  loop:          ", args.loop)

    reader = hddm_reader.HDDMReader(args.input_filename, args.batch_size, args.loop)

    context = zmq.Context.instance()
    socket = context.socket(zmq.PUSH)
    socket.bind(args.address)

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutting down...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    counter = 0
    next_send = time.monotonic()

    while running:
        now = time.monotonic()

        if now >= next_send:
            msg = reader.read_batch()
            if len(msg) == 0:
                break
            print("Sending events... which?")
            #socket.send(msg)
            #print(f"Sent: {msg!r}")

            counter += 1
            next_send += args.interval

        # Sleep just enough to avoid busy-waiting
        time.sleep(min(0.1, max(0.0, next_send - time.monotonic())))

    socket.close()
    context.term()
    print("Exited cleanly.")

