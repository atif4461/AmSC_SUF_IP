
import argparse
import time
import signal
import sys
import pandas
import os

import e2sar_py
from . import hddm_reader

ejfat_uri_str = os.getenv("EJFAT_URI"),


def add_arguments(parser):
    parser.add_argument("input_filename", help="Input REST filename")
    parser.add_argument("--name", default="source0", help="Name for this source")
    parser.add_argument("--address", default=ejfat_uri_str, help="Address of EJFAT load balancer")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval [s] between sends")
    parser.add_argument("--batch-size", type=int, default=1, help="Physics events per message")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True, help="Loop input file for infinite stream")
    parser.add_argument("--include-tables", help="Comma-separated list of tables (HDDM tags) to include")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")


def run(args):

    print("Running EJFAT source:")
    print("  input_filename: ", args.input_filename)
    print("  name:           ", args.name)
    print("  address:        ", args.address)
    print("  batch_size:     ", args.batch_size)
    print("  loop:           ", args.loop)
    print("  include_tables: ", args.include_tables)
    print("  verbose:        ", args.verbose)

    # Parse EJFAT_URI
    ejfat_uri = e2sar_py.EjfatURI(ejfat_uri_str, e2sar_py.EjfatURI.TokenType.instance)

    # Connect to the control plane and add self as a sender
    # TODO: Allocate an instance iff one hasn't been allocated for us
    manager = e2sar_py.ControlPlane.LBManager(ejfat_uri)
    result = manager.add_sender_self(False)

    if result.has_error():
        print("Error registering as sender: ", result.error().message)
        exit(1)

    # TODO: Not sure what event_source_id is and how it differs from data_id
    data_id = 0
    event_source_id = 0 #data_id

    # Create the Segmenter. Don't worry about multithreading here yet.
    segmenter = e2sar_py.DataPlane.Segmenter(
        ejfat_uri,
        data_id,
        event_source_id
    )

    # Fire up the segmenter
    segmenter.OpenAndStart()

    # Fire up the reader
    reader = hddm_reader.HDDMReader(args.input_filename, args.batch_size, args.loop)

    # Loop until killed
    running = True
    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutdown requested...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    event_nr = 0
    while running:

        msg = reader.read_batch()
        if not msg:
            break
        if args.verbose:
            msg.print_selected(include_tables)
        else:
            msg.print_short()

        # Convert message to bytes
        data = msg.to_arrow()

        # Send message
        segmenter.addToSendQueue(data, len(data), _eventNum=event_nr)

        time.sleep(1) # seconds
        event_nr += 1

    # Shut down segmenter threads
    print("Joining threads...")
    segmenter.stopThreads()
    print("Shutdown complete.")



