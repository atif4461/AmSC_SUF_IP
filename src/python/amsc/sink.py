
import argparse
import zmq
import signal
import sys

ADDRESS = "tcp://*:5556"

def add_arguments(parser):
    parser.add_argument("--input-address", default=ADDRESS, help="Input address of ZMQ socket")
    parser.add_argument("--output-bucket", default=ADDRESS, help="Input address of ZMQ socket")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")


def process_fake_data(data: bytes) -> None:
    print(f"Received {len(data)} bytes: {data!r}")


def process_real_data(data: bytes) -> None:
    print(f"Received {len(data)} bytes: {data!r}")


def run(args):

    print("Running sink:")
    print("  input_address: ", args.input_address)
    print("  real_data:     ", args.real_data)

    context = zmq.Context.instance()
    socket = context.socket(zmq.PULL)
    socket.bind(args.input_address)

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutting down...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    while running:
        print("Polling for incoming events...")
        events = dict(poller.poll(timeout=1000))  # 1s timeout

        if socket in events:
            try:
                msg = socket.recv(flags=zmq.NOBLOCK)
                if (args.real_data):
                    process_real_data(msg)
                else:
                    process_fake_data(msg)
            except zmq.Again:
                # No message available (race with poll)
                continue

    socket.close()
    context.term()
    print("Exited cleanly.")



