
import argparse

def add_arguments(parser):
    parser.add_argument("--name", default="worker0", help="Name for this worker")
    parser.add_argument("--input-address", default="localhost:12345", help="Input address of load balancer or ZMQ socket")
    parser.add_argument("--output-address", default="localhost:12346", help="Output address of ZMQ socket")
    parser.add_argument("--ejfat", action=argparse.BooleanOptionalAction, default=False, help="Use EJFAT load balancer")
    parser.add_argument("--real-data", action=argparse.BooleanOptionalAction, default=False, help="Use real GlueX data")

def run(args):
    print("Running worker:")
    print("  name:           ", args.name)
    print("  input_address:  ", args.input_address)
    print("  output_address: ", args.output_address)
    print("  use_ejfat:      ", args.ejfat)
    print("  use_real_data:  ", args.real_data)

