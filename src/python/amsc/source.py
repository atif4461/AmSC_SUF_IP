
import argparse
import time
import signal
import sys
import pandas
import os

import e2sar_py
from amsc import hddm_reader,credentials


def add_arguments(parser):
    parser.add_argument("input_filename", help="Input REST filename")
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--name", default="source0", help="Name for this source")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval [s] between sends")
    parser.add_argument("--batch-size", type=int, default=1, help="Physics events per message")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True, help="Loop input file for infinite stream")
    parser.add_argument("--include-tables", help="Comma-separated list of tables (HDDM tags) to include")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")


def run(args):

    print("Running EJFAT source:")
    print("  input_filename: ", args.input_filename)
    print("  credential_dir: ", args.credential_dir)
    print("  name:           ", args.name)
    print("  batch_size:     ", args.batch_size)
    print("  loop:           ", args.loop)
    print("  include_tables: ", args.include_tables)
    print("  verbose:        ", args.verbose)
    print()

    VALIDATE = False
    USE_IPV6 = False
    USE_HOST_ADDRESS = True

    ejfat_uri = credentials.get_ejfat_uri_raw(args.credential_dir)
    print("  ejfat_uri_raw:  ", ejfat_uri)

    # Connect to the control plane and add self as a sender
    manager = e2sar_py.ControlPlane.LBManager(ejfat_uri, VALIDATE, USE_HOST_ADDRESS)
    result = manager.add_sender_self(USE_IPV6)

    if result.has_error():
        print("Error registering as sender: ", result.error().message)
        exit(1)

    # TODO: Not sure what event_source_id is and how it differs from data_id
    data_id = 0
    event_source_id = 0 #data_id

    # Create the Segmenter. Don't worry about multithreading here yet.
    flags = e2sar_py.DataPlane.Segmenter.SegmenterFlags()
    flags.useCP = True
    flags.dpV6 = USE_IPV6

    segmenter = e2sar_py.DataPlane.Segmenter(
        ejfat_uri,
        data_id,
        event_source_id,
        flags
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
            msg.print_selected(args.include_tables)
        else:
            msg.print_short()

        # Convert message to bytes
        data = msg.to_arrow()

        # Send message
        #res = segmenter.addToSendQueue(data, len(data), _eventNum=event_nr)
        res = segmenter.sendEvent(data, len(data), _eventNum=event_nr)
        if res.has_error():
            print("Error:", res.error())

        time.sleep(args.interval) # seconds
        event_nr += 1

    # Shut down segmenter threads
    print("Joining threads...")
    segmenter.stopThreads()
    print("Shutdown complete.")



