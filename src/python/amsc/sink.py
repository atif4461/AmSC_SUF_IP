
import argparse

def add_arguments(parser):
    parser.add_argument("--input-address", default="localhost:12345", help="Input address of ZMQ socket")
    parser.add_argument("--real-data", action=argparse.BooleanOptionalAction, default=False, help="Use real GlueX data")

def run(args):
    print("Running sink:")
    print("  input_address: ", args.input_address)
    print("  use_real_data: ", args.real_data)


