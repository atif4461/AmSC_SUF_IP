
import argparse
import zmq
import signal
import sys
import socket
import numpy
from amsc import message

INPUT_ADDRESS = "tcp://*:5556"
min_entry_observed = -1
max_entry_observed = -1
missing_events = set()

def add_arguments(parser):
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")
    parser.add_argument("--input-address", default=INPUT_ADDRESS, help="Address of upstream ZMQ socket (owned by sink)")
    #parser.add_argument("--output-address", help="Address of downstream ZMQ socket (owned by source)")


def process_data(data: bytes, verbose) -> None:
    global max_entry_observed
    global min_entry_observed
    global missing_events

    print(f"Received {len(data)} bytes")
    msg = message.Message.from_arrow(data)
    if verbose:
        msg.print_all()
    else:
        msg.print_short()

    # Extract entry numbers from batch
    df = msg["reconstructedPhysicsEvent"]

    new_min_entry = df["entry"].min()
    new_max_entry = df["entry"].max()

    for entry_nr in range(max_entry_observed+1, new_min_entry):
        missing_events.add(entry_nr)

    for entry_nr in df["entry"]:
        if entry_nr in missing_events:
            missing_events.remove(entry_nr)

    if new_max_entry > max_entry_observed:
        max_entry_observed = new_max_entry

    all_missing_events = numpy.fromiter(sorted(missing_events), int)
    print("Missing events: ")
    print(sorted(missing_events))
    if (max_entry_observed > 0):
        print(f"{len(missing_events)}/{max_entry_observed} ({len(missing_events)/max_entry_observed*100:.2f}%) lost")
    return all_missing_events.tobytes()


def run(args):

    print("Running sink:")
    print("  input_address: ", args.input_address)
    print("  verbose:       ", args.verbose)

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
                result = process_data(msg, args.verbose)

            except zmq.Again:
                # No message available (race with poll)
                continue

    socket.close()
    context.term()
    print("Exited cleanly.")



