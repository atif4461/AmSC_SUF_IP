#!/usr/bin/env python3

import e2sar_py
import os
import signal
import time


def main():
    # Retrieve EJFAT_URI
    ejfat_uri_str = os.getenv("EJFAT_URI")
    print("Launching worker with EJFAT_URI=", ejfat_uri_str)

    # Parse EJFAT_URI
    ejfat_uri = e2sar_py.EjfatURI(ejfat_uri_str, e2sar_py.EjfatURI.TokenType.instance)

    # Not sure what these numbers are supposed to be, exactly
    starting_port = 8888
    thread_count = 1

    # Create the Segmenter. Don't worry about multithreading here yet.
    reassembler = e2sar_py.DataPlane.Reassembler(
        ejfat_uri,
        starting_port,
        thread_count
    )

    print("    data_ip=", reassembler.get_dataIP())
    print("    port_range=", reassembler.get_portRange())
    print("    recv_ports=", reassembler.get_recvPorts())

    print("Registering worker 'myworker'...")
    reassembler.registerWorker("myworker")

    print("Launching threads...")

    # Fire up the reassembler
    reassembler.OpenAndStart()

    print("Threads are now running")

    # Loop until killed
    running = True
    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutdown requested...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while running:

        # Receive message
        wait_ms = 3000
        evt_length, evt_bytes, evt_nr, data_id = reassembler.recvEventBytes(wait_ms)

        if evt_length >= 0:
            message = evt_bytes.split(b"\x00", 1)[0].decode("utf-8")
            print(f"Received evt {evt_nr} from src {data_id} containing: {message}")
        else:
            print("Waiting for incoming events...")


    print("Deregistering worker...")
    reassembler.deregisterWorker()

    print("Joining threads...")
    reassembler.stopThreads()

    print("Shutdown complete.")


if __name__ == "__main__":
    main()


