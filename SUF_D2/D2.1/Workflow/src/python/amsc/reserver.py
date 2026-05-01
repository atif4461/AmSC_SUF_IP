
import subprocess
import os
import argparse
import sys
import pathlib
from amsc import credentials

def add_arguments(parser):
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--name", default="amsc_demo_2.1", help="Name of reservation")
    parser.add_argument("--duration", default="01:00:00", help="Duration of reservation")


def run(args):

    print("Reserving EJFAT load balancer instance")
    print("  credential_dir:  ", args.credential_dir)
    print("  name:            ", args.name)
    print("  duration:        ", args.duration)

    reserve_ejfat(args.credential_dir, args.name, args.duration)


def reserve_ejfat(credential_dir, name, duration):

    admin_token = credentials.get_ejfat_uri(credential_dir, "ejfat_uri_admin.txt")

    result = subprocess.run(
        ["lbadm", "--reserve", "-l", name + "_raw", "-u", admin_token, "-d", duration, "-4", "--export"],
        capture_output=True, text=True, check=True
    )

    credentials.put_ejfat_uri_raw(credential_dir, result.stdout)


    result = subprocess.run(
        ["lbadm", "--reserve", "-l", name + "_processed", "-u", admin_token, "-d", duration, "-4", "--export"],
        capture_output=True, text=True, check=True
    )

    credentials.put_ejfat_uri_processed(credential_dir, result.stdout)

