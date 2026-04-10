
import argparse
import zmq
import signal
import sys
import random
from amsc import message

PULL_ADDRESS = "tcp://localhost:5555"
PUSH_ADDRESS = "tcp://localhost:5556"

def add_arguments(parser):
    parser.add_argument("--name", default="worker0", help="Name for this worker")
    parser.add_argument("--input-address", default=PULL_ADDRESS, help="Address of upstream ZMQ socket")
    parser.add_argument("--output-address", default=PUSH_ADDRESS, help="Address of downstream ZMQ socket")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")
    parser.add_argument("--unreliable", action=argparse.BooleanOptionalAction, default=False, help="Simulate EJFAT transmission errors")


def process_data(serialized_data: bytes, verbose: bool) -> bytes:
    print(f"Received {len(serialized_data)} bytes")
    msg = message.Message.from_arrow(serialized_data)
    if verbose:
        msg.print_all()
    else:
        msg.print_short()

    # TODO: Eventually calculate something here. In the meantime, just forward the event headers
    event_header = msg["reconstructedPhysicsEvent"]
    output_message = message.Message({"reconstructedPhysicsEvent":(event_header,-1,-1)})
    return output_message.to_arrow()


def run(args):
    print("Running worker:")
    print("  name:           ", args.name)
    print("  input_address:  ", args.input_address)
    print("  output_address: ", args.output_address)
    print("  verbose:        ", args.verbose)
    print("  unreliable:     ", args.unreliable)
    print()

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

        print("Waiting for incoming events...")
        events = dict(poller.poll(timeout=1000))  # 1s timeout

        if pull_sock in events:
            try:
                msg = pull_sock.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                continue

            if (args.unreliable and (random.uniform(0,1) < 0.1)):
                print("==============================================================")
                print("Simulating a transmission failure by dropping incoming message")
                print("==============================================================")
            else:
                result = process_data(msg, args.verbose)
                push_sock.send(result)


    pull_sock.close()
    push_sock.close()
    context.term()
    print("Exited cleanly.")

