
import e2sar_py
import os
import signal
import time
import argparse


def run_worker(
        ejfat_uri_str = os.getenv("EJFAT_URI"),
        worker_id = 0,
        starting_port = 12345,
        thread_count = 1
    ):

    # Retrieve EJFAT_URI
    print("Launching worker ", worker_id, " with EJFAT_URI=", ejfat_uri_str)

    # Parse EJFAT_URI
    ejfat_uri = e2sar_py.EjfatURI(ejfat_uri_str, e2sar_py.EjfatURI.TokenType.instance)

    # Create the Segmenter. Don't worry about multithreading here yet.
    reassembler = e2sar_py.DataPlane.Reassembler(
        ejfat_uri,
        starting_port,
        thread_count
    )

    print("    data_ip=", reassembler.get_dataIP())
    print("    port_range=", reassembler.get_portRange())
    print("    recv_ports=", reassembler.get_recvPorts())

    # Register worker
    worker_name = "worker" + str(worker_id)
    print(f"Registering worker '{worker_name}'...")
    result = reassembler.registerWorker(worker_name)
    if result.has_error():
        print("Error registering as worker: ", result.error().message)
        exit(1)

    # Fire up the reassembler
    print("Launching threads...")
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
            print(f"Received evt {evt_nr} from src {data_id} of length {evt_length} containing: {evt_bytes}")
        else:
            print("Waiting for incoming events...")


    print("Deregistering worker...")
    reassembler.deregisterWorker()

    print("Joining threads...")
    reassembler.stopThreads()

    print("Shutdown complete.")


def main():

    parser = argparse.ArgumentParser(
        description="Run a simple example EJFAT worker."
    )

    parser.add_argument(
        "--url",
        dest="url_str",
        type=str,
        default=os.getenv("EJFAT_URI"),
        help="EJFAT_URI with instance token, e.g. ejfats://$TOKEN_GOES_HERE@ejfat-1.jlab.org:18347/lb/$LB_ID",
    )
    parser.add_argument(
        "--id",
        dest="worker_id",
        type=int,
        default=0,
        help="Unique worker ID",
    )
    parser.add_argument(
        "--starting-port",
        type=int,
        default=12345,
        help="Starting port number for this worker",
    )
    parser.add_argument(
        "--thread-count",
        type=int,
        default=1,
        help="Number of threads to use for reassembly",
    )

    args = parser.parse_args()

    run_worker(
        ejfat_uri_str = args.url_str,
        worker_id = args.worker_id,
        starting_port = args.starting_port,
        thread_count = args.thread_count,
    )


if __name__ == "__main__":
    main()


