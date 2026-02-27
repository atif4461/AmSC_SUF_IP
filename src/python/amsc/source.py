
import argparse

def add_arguments(parser):

    parser.add_argument("--name", default="source0", help="Name for this source")
    parser.add_argument("--address", default="localhost:12345", help="Address of load balancer or ZMQ socket")
    parser.add_argument("--ejfat", action=argparse.BooleanOptionalAction, default=False, help="Stream over EJFAT load balancer")
    parser.add_argument("--real-data", action=argparse.BooleanOptionalAction, default=False, help="Stream real GlueX data")

def run(args):
    print("Running source:")
    print("  name:          ", args.name)
    print("  address:       ", args.address)
    print("  use_ejfat:     ", args.ejfat)
    print("  use_real_data: ", args.real_data)

