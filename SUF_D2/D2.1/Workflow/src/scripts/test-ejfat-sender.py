#!/usr/bin/env python3
"""Test raw EJFAT delivery with generated events or a preloaded real HDDM batch."""

import argparse
import time

import pandas as pd

from amsc import credentials, ejfat, message
from amsc.bandwidth import format_payload_rate


def make_payload(batch_size):
    events = pd.DataFrame({
        "eventNo": range(batch_size),
        "runNo": [0] * batch_size,
    })
    return message.Message({
        "reconstructedPhysicsEvent": (events, -1, -1),
    }).to_arrow()


def make_hddm_payload(filename, batch_size):
    from amsc.hddm_reader import HDDMReader

    reader = HDDMReader(filename, batch_size, loop=False)
    batch = reader.read_batch()
    if batch is None:
        raise ValueError("The HDDM input file contains no events")
    print(f"Loaded {len(batch['reconstructedPhysicsEvent'])} real HDDM events", flush=True)
    return batch.to_arrow()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir)
    parser.add_argument("--count", type=int, default=60, help="Number of batches to send")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between batches")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--input-file", help="HDDM file; preload and repeat its first batch")
    parser.add_argument("--ip", help="Sender IPv4 address registered with EJFAT")
    parser.add_argument("--id", type=int, default=0)
    parser.add_argument("--stats-every", type=float, default=3.0)
    args = parser.parse_args()
    if args.count < 1 or args.batch_size < 1 or args.interval < 0 or args.stats_every <= 0:
        parser.error("count, batch-size and stats-every must be positive; interval must be nonnegative")

    if args.input_file:
        payload = make_hddm_payload(args.input_file, args.batch_size)
    else:
        payload = make_payload(args.batch_size)
    print(f"Preloaded Arrow payload: {len(payload)} bytes; interval={args.interval}s", flush=True)
    sender = ejfat.EjfatSender(
        credentials.get_ejfat_uri_raw(args.credential_dir),
        event_source_id=args.id,
        ip_addr=args.ip,
    )
    sender.connect()
    t0 = time.monotonic()
    queued_bytes = 0
    try:
        for batch in range(args.count):
            sender.send(payload)
            queued_bytes += len(payload)
            print(f"Queued raw batch {batch + 1}/{args.count}: {len(payload)} bytes", flush=True)
            time.sleep(args.interval)
            now = time.monotonic()
            if now - t0 >= args.stats_every or batch == args.count - 1:
                print(format_payload_rate("raw_tx_queued", queued_bytes, now - t0), flush=True)
                queued_bytes = 0
                t0 = now
        # Give the asynchronous segmenter time to transmit the last queued batch.
        time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping test sender.", flush=True)
    finally:
        sender.disconnect()
    print("Done. Confirm delivery using the receiving worker's processed count.", flush=True)


if __name__ == "__main__":
    main()
