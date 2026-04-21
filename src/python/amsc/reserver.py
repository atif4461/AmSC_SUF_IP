
import subprocess
import os
import argparse
import sys
from amsc import credentials

ejfat_uri_str = os.getenv("EJFAT_URI")

def add_arguments(parser):
    parser.add_argument("--address", default=ejfat_uri_str, help="Address of EJFAT load balancer")
    parser.add_argument("--name", default="amsc_demo_2.1", help="Name of reservation")
    parser.add_argument("--duration", default="01:00:00", help="Duration of reservation")

def run(args):

    print("Reserving EJFAT load balancer instance")
    print("  address:  ", args.address)
    print("  name:     ", args.name)
    print("  duration: ", args.duration)

    if args.address is None:
        print("Error: EJFAT_URI was not provided via $EJFAT_URI or --address")
        sys.exit(1)

    # TODO: Check that file doesn't already exist

    result = subprocess.run(
        ["lbadm", "--reserve", "-l", args.name + "_raw", "-d", args.duration, "-4", "--export"],
        capture_output=True, text=True, check=True
    )

    credentials.put_ejfat_uri_raw(args.credential_dir, result.stdout)


    result = subprocess.run(
        ["lbadm", "--reserve", "-l", args.name + "_processed", "-d", args.duration, "-4", "--export"],
        capture_output=True, text=True, check=True
    )

    credentials.put_ejfat_uri_processed(args.credential_dir, result.stdout)

