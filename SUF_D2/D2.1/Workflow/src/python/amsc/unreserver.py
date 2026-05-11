
import subprocess
import os
import argparse
import sys
import pathlib
from amsc import credentials

def add_arguments(parser):
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")

def run(args):

    print("Unreserving EJFAT load balancer instance")
    print("  credential_dir:  ", args.credential_dir)

    unreserve_ejfat(args.credential_dir)


def unreserve_ejfat(credential_dir):

    print("Freeing ejfat_uri_raw...")
    raw_token = credentials.get_ejfat_uri(credential_dir, "ejfat_uri_raw.txt")
    try:
        result = subprocess.run(
            ["lbadm", "--free", "-u", raw_token],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError:
        pass

    print("Freeing ejfat_uri_processed...")
    processed_token = credentials.get_ejfat_uri(credential_dir, "ejfat_uri_processed.txt")
    try:
        result = subprocess.run(
            ["lbadm", "--free", "-u", processed_token],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError:
        pass

    credentials.clear(credential_dir)
    print("Success")


