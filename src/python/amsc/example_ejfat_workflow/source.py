
import e2sar_py
import os
import signal
import time
import argparse

def create_message(source_id, event_nr):
    return f"Source {source_id} proudly presents event {event_nr} for your viewing pleasure."


def run_source(
        ejfat_uri_str = os.getenv("EJFAT_URI"),
        data_id = 0
    ):

    print("Launching source with EJFAT_URI=", ejfat_uri_str)

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
    event_source_id = 0 #data_id

    # Create the Segmenter. Don't worry about multithreading here yet.
    segmenter = e2sar_py.DataPlane.Segmenter(
        ejfat_uri,
        data_id,
        event_source_id
    )

    # Fire up the segmenter
    segmenter.OpenAndStart()

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
        message = create_message(event_source_id, event_nr)
        print("Emitting message: ", message)

        # Convert message to bytes
        data = message.encode("utf-8")

        # Send message
        segmenter.addToSendQueue(data, len(data), _eventNum=event_nr)

        time.sleep(1) # seconds
        event_nr += 1

    # Shut down segmenter threads
    print("Joining threads...")
    segmenter.stopThreads()
    print("Shutdown complete.")


def main():

    parser = argparse.ArgumentParser(
        description="Run a simple example EJFAT source."
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
        dest="data_id",
        type=int,
        default=0,
        help="Unique data ID",
    )

    args = parser.parse_args()

    run_source(
        ejfat_uri_str = args.url_str,
        data_id = args.data_id,
    )


if __name__ == "__main__":
    main()
