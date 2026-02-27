
import argparse
import zmq
import signal
import sys

PULL_ADDRESS = "tcp://localhost:5555"
PUSH_ADDRESS = "tcp://localhost:5556"

def add_arguments(parser):
    parser.add_argument("--name", default="worker0", help="Name for this worker")
    parser.add_argument("--input-address", default=PULL_ADDRESS, help="Input address of load balancer or ZMQ socket")
    parser.add_argument("--output-address", default=PUSH_ADDRESS, help="Output address of ZMQ socket")
    parser.add_argument("--ejfat", action=argparse.BooleanOptionalAction, default=False, help="Use EJFAT load balancer")
    parser.add_argument("--real-data", action=argparse.BooleanOptionalAction, default=False, help="Use real GlueX data")

def process_fake_data(data: bytes) -> bytes:
    # Example: uppercase transform
    print(f"Received {len(data)} bytes: {data!r}")
    result = data.upper()
    print(f"Sending: {result!r}")
    return result

def process_real_data(data: bytes) -> bytes:
    # Example: uppercase transform
    print(f"Received {len(data)} bytes")
    return data.upper()

def run(args):
    print("Running worker:")
    print("  name:           ", args.name)
    print("  input_address:  ", args.input_address)
    print("  output_address: ", args.output_address)
    print("  use_ejfat:      ", args.ejfat)
    print("  use_real_data:  ", args.real_data)

    context = zmq.Context.instance()

    pull_sock = context.socket(zmq.PULL)
    pull_sock.connect(args.input_address)

    push_sock = context.socket(zmq.PUSH)
    push_sock.connect(args.output_address)

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutting down...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    poller = zmq.Poller()
    poller.register(pull_sock, zmq.POLLIN)

    while running:

        print("Polling for incoming events...")
        events = dict(poller.poll(timeout=1000))  # 1s timeout

        if pull_sock in events:
            try:
                msg = pull_sock.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                continue

            if args.real_data:
                result = process_real_data(msg)
                push_sock.send(result)
            else:
                result = process_fake_data(msg)
                push_sock.send(result)

    pull_sock.close()
    push_sock.close()
    context.term()
    print("Exited cleanly.")


