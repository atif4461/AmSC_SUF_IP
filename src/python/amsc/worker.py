import e2sar_py
import zmq
import os
import signal
import time
import argparse
from . import message


EJFAT_URI_STR = os.getenv("EJFAT_URI")
STARTING_PORT = 10000
PUSH_ADDRESS = "tcp://localhost:5556"

def add_arguments(parser):
    parser.add_argument("--name", default="worker0", help="Name for this worker")
    parser.add_argument("--ejfat-uri", default=EJFAT_URI_STR, help="Address of EJFAT load balancer")
    parser.add_argument("--input-port", type=int, default=STARTING_PORT, help="Port for EJFAT to stream to")
    parser.add_argument("--output-address", default=PUSH_ADDRESS, help="Address of downstream ZMQ socket")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")


def process_data(serialized_data: bytes, verbose: bool) -> bytes:
    print(f"Received {len(serialized_data)} bytes")
    msg = message.Message.from_arrow(serialized_data)
    if verbose:
        msg.print_all()
    else:
        msg.print_short()

    # TODO: Eventually calculate something here. In the meantime, just forward the event headers
    event_header = msg["reconstructedPhysicsEvent"]
    output_message = message.Message({"reconstructedPhysicsEvent":(event_header,-1,-1)})
    return output_message.to_arrow()


def run(args):

    print("Running worker:")
    print("  name:           ", args.name)
    print("  ejfat_uri:      ", args.ejfat_uri)
    print("  input_port:     ", args.input_port)
    print("  output_address:   ", args.output_address)
    print("  verbose:        ", args.verbose)
    print()

    USE_IPV6 = False

    # Parse EJFAT_URI
    ejfat_uri = e2sar_py.EjfatURI(args.ejfat_uri, e2sar_py.EjfatURI.TokenType.instance, USE_IPV6)

    # Create the reassembler
    thread_count = 4
    flags = e2sar_py.DataPlane.Reassembler.ReassemblerFlags()
    flags.useCP = True
    flags.validateCert = False
    flags.eventTimeout_ms = 3000

    reassembler = e2sar_py.DataPlane.Reassembler(
        ejfat_uri,
        args.input_port,
        thread_count,
        flags
    )

    print("Created E2SAR reassembler:")
    print("    data_ip=", reassembler.get_dataIP())
    print("    port_range=", reassembler.get_portRange())
    print("    recv_ports=", reassembler.get_recvPorts())

    # Register worker
    print(f"Registering worker '{args.name}'...")
    result = reassembler.registerWorker(args.name)
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

        print("Waiting for incoming events...")

        # Receive message
        wait_ms = 3000
        evt_length, evt_bytes, evt_nr, data_id = reassembler.recvEventBytes(wait_ms)

        if evt_length >= 0:
            print(f"Received evt {evt_nr} from src {data_id} of length {evt_length}")
            output_message = process_data(evt_bytes, args.verbose)


    print("Deregistering worker...")
    reassembler.deregisterWorker()

    print("Joining threads...")
    reassembler.stopThreads()

    print("Exited cleanly.")

