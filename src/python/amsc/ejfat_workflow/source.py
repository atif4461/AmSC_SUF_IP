
import e2sar_py
import os
import signal
import time

def create_message(source_id, event_nr):
    return f"Source {source_id} proudly presents event {event_nr} for your viewing pleasure."


def main():
    # Retrieve EJFAT_URI
    ejfat_uri_str = os.getenv("EJFAT_URI")
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
    else:
        print("add_sender_self returned with status code: ", result.value())



    # Not sure what these numbers are supposed to be, exactly
    data_id = 0
    event_source_id = 0

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
        segmenter.addToSendQueue(data, event_nr)

        time.sleep(1) # seconds
        event_nr += 1


    # Shut down segmenter threads
    print("Joining threads...")
    segmenter.stopThreads()
    print("Shutdown complete.")


if __name__ == "__main__":
    main()


