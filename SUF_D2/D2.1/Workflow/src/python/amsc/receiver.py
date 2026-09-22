"""
Simple EJFAT receiver for bandwidth measurement.
Receives raw events from source, counts bytes/events, reports throughput.
No ZMQ, no Arrow deserialization, no physics processing.
"""

import argparse
import signal
import time
import sys

from amsc import credentials, ejfat


def add_arguments(parser):
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing EJFAT credentials")
    parser.add_argument("--input-port", type=int, default=19800, help="Port for EJFAT to stream data back to")
    parser.add_argument("--stats-every", type=float, default=1.0, help="Print stats every N seconds")
    parser.add_argument("--ip", type=str, default=None, help="IP address to register with LB (defaults to autoip)")
    parser.add_argument("--name", type=str, default="bw_receiver", help="Receiver name for EJFAT registration")


def run_receiver(args):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    ejfat_uri_raw = credentials.get_ejfat_uri_raw(args.credential_dir)
    print(f"Connecting to EJFAT raw stream: {ejfat_uri_raw}")

    receiver = ejfat.EjfatReceiver(args.name, ejfat_uri_raw, args.ip, args.input_port)
    receiver.connect()

    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutdown requested...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    total_bytes = 0
    total_events = 0
    t0 = time.monotonic()

    print(f"Receiving on port {args.input_port}... (Ctrl+C to stop)")

    while running:
        evt_length, evt_bytes, evt_nr, data_id = receiver.recv(100)
        if evt_length > 0:
            total_bytes += evt_length
            total_events += 1

        t1 = time.monotonic()
        if (t1 - t0) >= args.stats_every:
            elapsed = t1 - t0
            rate_mbps = (total_bytes * 8) / elapsed / 1e6
            rate_mbs = total_bytes / elapsed / 1e6
            evt_rate = total_events / elapsed
            print(
                f"  Events: {total_events:6d}  "
                f"Bytes: {total_bytes/1e6:8.2f} MB  "
                f"Rate: {rate_mbs:8.2f} MB/s ({rate_mbps:6.2f} Mbps)  "
                f"Event rate: {evt_rate:6.1f} Hz"
            )
            t0 = t1
            total_bytes = 0
            total_events = 0

    print("Disconnecting EJFAT receiver...")
    receiver.disconnect()
    print("Done.")


def run(args):
    print("Running bandwidth receiver:")
    print(f"  credential_dir: {args.credential_dir}")
    print(f"  input_port:     {args.input_port}")
    print(f"  stats_every:    {args.stats_every}")
    print(f"  ip:             {args.ip}")
    print(f"  name:           {args.name}")
    print()
    run_receiver(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EJFAT bandwidth receiver")
    add_arguments(parser)
    args = parser.parse_args()
    run(args)