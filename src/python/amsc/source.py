
import argparse
import time
import signal
import sys
import pandas
import os

import e2sar_py
from amsc import hddm_reader,credentials,ejfat


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


    ejfat_uri_raw = credentials.get_ejfat_uri_raw(args.credential_dir)
    print("  ejfat_uri_raw:  ", ejfat_uri_raw)

    ejfat_uri_processed = credentials.get_ejfat_uri_processed(args.credential_dir)
    print("  ejfat_uri_processed:  ", ejfat_uri_processed)

    ejfat_sender = EjfatSender(ejfat_uri_raw)
    sender.connect()

    ejfat_receiver = EjfatReceiver(ejfat_uri_processed)
    receiver.connect()

    # Fire up the HDDM reader
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
        ejfat_sender.send(data, event_nr)

        # Quickly check if we've received something
        evt_length, evt_bytes, evt_nr, data_id = ejfat_receiver.recv(0)
        if evt_length >= 0:
            print(f"Received response: {evt_bytes}")

        time.sleep(args.interval) # seconds
        event_nr += 1


    ejfat_sender.disconnect()
    ejfat_receiver.disconnect()



