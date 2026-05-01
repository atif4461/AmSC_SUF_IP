

import pathlib
import time
import socket
import os


default_credential_dir = "/cred"

sink_filename = "zmq_uri_sink.txt"
raw_filename = "ejfat_uri_raw.txt"
processed_filename = "ejfat_uri_processed.txt"


def get_zmq_address(credential_dir):

    filepath = pathlib.Path(credential_dir) / sink_filename

    while not filepath.exists():
        print(f"Waiting for ZMQ URI to be written at {filepath}")
        time.sleep(1)

    with open(filepath, 'r') as f:
        line = f.readlines()[0]
        return line.strip()


def put_zmq_address(credential_dir):

    temp_filepath = pathlib.Path(credential_dir) / (sink_filename + ".tmp")
    final_filepath = pathlib.Path(credential_dir) / sink_filename

    #if final_filepath.exists():
    #    raise Exception(f"ZMQ URI already present in credential directory: {final_filepath}")

    zmq_uri = "tcp://" + socket.gethostname() + ":5555"

    with open(temp_filepath, 'w') as f:
        f.write(zmq_uri)

    # Perform an (atomic) rename so that other processes can sync on the complete file
    os.rename(temp_filepath, final_filepath)

    print(f"Successfully wrote ZMQ URI:")
    print("    contents    = ", zmq_uri)
    print("    destination = ", final_filepath)
    print()

    return zmq_uri


def get_ejfat_uri(credential_dir, filename):

    filepath = pathlib.Path(credential_dir) / filename

    while not filepath.exists():
        print(f"Waiting for EJFAT URI to be written at {filepath}")
        time.sleep(1)

    with open(filepath, 'r') as f:
        line = f.readlines()[0]
        line = line.strip()
        line = line.removeprefix("export EJFAT_URI='")
        line = line.removesuffix("'")
        return line


def get_ejfat_uri_raw(credential_dir):
    return get_ejfat_uri(credential_dir, raw_filename)

def get_ejfat_uri_processed(credential_dir):
    return get_ejfat_uri(credential_dir, processed_filename)


def put_ejfat_uri(credential_dir, filename, ejfat_uri):

    temp_filepath = pathlib.Path(credential_dir) / (filename + ".tmp")
    final_filepath = pathlib.Path(credential_dir) / filename

    if final_filepath.exists():
        raise Exception(f"EJFAT URI already present in credential directory: {final_filepath}")

    with open(temp_filepath, 'w') as f:
        f.write(ejfat_uri)

    # Perform an (atomic) rename so that other processes can sync on the complete file
    os.rename(temp_filepath, final_filepath)

    print(f"Successfully wrote EJFAT URI:")
    print("    contents    = ", ejfat_uri)
    print("    destination = ", final_filepath)
    print()


def put_ejfat_uri_raw(credential_dir, ejfat_uri):
    put_ejfat_uri(credential_dir, raw_filename, ejfat_uri)

def put_ejfat_uri_processed(credential_dir, ejfat_uri):
    put_ejfat_uri(credential_dir, processed_filename, ejfat_uri)



