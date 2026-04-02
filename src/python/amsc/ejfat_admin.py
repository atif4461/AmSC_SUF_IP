
import subprocess
import os
import argparse

ejfat_uri_str = os.getenv("EJFAT_URI")

def add_arguments(parser):
    parser.add_argument("--address", default=ejfat_uri_str, help="Address of EJFAT load balancer")
    parser.add_argument("--name", default="nbrei_amsc_demo", help="Name of reservation")
    parser.add_argument("--duration", default="01:00:00", help="Duration of reservation")

def run(args):

    print("Reserving EJFAT load balancer instance")
    print("  address:  ", args.address)
    print("  name:     ", args.name)
    print("  duration: ", args.duration)

    result = subprocess.run(
        ["lbadm", "--reserve", "-l", args.name, "-d", args.duration, "-4", "--export"],
        capture_output=True, text=True, check=True
    )

    with open("instance.env", "w") as f:
        f.write(result.stdout)


