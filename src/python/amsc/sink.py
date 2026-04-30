
import argparse
import zmq
import signal
import sys
import socket
import numpy
import e2sar_py

from amsc import message,credentials,ejfat

min_entry_observed = -1
max_entry_observed = -1
missing_events = set()

def add_arguments(parser):
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")


def process_data(data: bytes, verbose) -> bytes:
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
    print("    credential_dir: ", args.credential_dir)
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


    while running:
        print("Polling for incoming events...")
        events = dict(poller.poll(timeout=1000))  # 1s timeout

        if socket in events:
            try:
                msg = socket.recv(flags=zmq.NOBLOCK)
                result = process_data(msg, args.verbose) # Returns bytes
                ejfat_sender.send(result)

            except zmq.Again:
                # No message available (race with poll)
                continue

    socket.close()
    context.term()

    ejfat_sender.disconnect()

    print("Exited cleanly.")



