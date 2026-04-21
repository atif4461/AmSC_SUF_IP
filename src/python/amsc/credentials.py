

import e2sar_py
import pathlib
import time


default_credential_dir = "/testbed/home/nbrei/amsc_demo"

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

    filepath = pathlib.Path(credential_dir) / sink_filename

    if filepath.exists():
        raise Exception(f"ZMQ URI already present in credential directory: {filepath}")

    zmq_uri = "asdf"

    with open(filepath, 'w') as f:
        f.write(zmq_uri)

    return zmq_uri


def get_ejfat_uri(credential_dir, filename, token_type):

    filepath = pathlib.Path(credential_dir) / filename

    while not filepath.exists():
        print(f"Waiting for EJFAT URI to be written at {filepath}")
        time.sleep(1)

    with open(filepath, 'r') as f:
        line = f.readlines()[0]
        line = line.removeprefix("export EJFAT_URI='")
        line = line.removesuffix("'\n")
        ejfat_uri = e2sar_py.EjfatURI.get_from_file(line, token_type)
        return ejfat_uri


def get_ejfat_uri_raw(credential_dir):
    return get_ejfat_uri(credential_dir, raw_filename, e2sar_py.EjfatURI.TokenType.instance)

def get_ejfat_uri_processed(credential_dir):
    return get_ejfat_uri(credential_dir, processed_filename, e2sar_py.EjfatURI.TokenType.instance)


def put_ejfat_uri(credential_dir, filename, ejfat_uri):

    filepath = pathlib.Path(credential_dir) / filename

    if filepath.exists():
        raise Exception(f"EJFAT URI already present in credential directory: {filepath}")

    with open(filepath, 'w') as f:
        f.write(ejfat_uri)


def put_ejfat_uri_raw(credential_dir, ejfat_uri):
    put_ejfat_uri(credential_dir, raw_filename, ejfat_uri)

def put_ejfat_uri_processed(credential_dir, ejfat_uri):
    put_ejfat_uri(credential_dir, processed_filename, ejfat_uri)



