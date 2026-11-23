import argparse
import multiprocessing as mp
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import zmq

from amsc import sink


def run_sink_without_ejfat(args, received):
    class RecordingSender:
        def __init__(self, *args):
            pass

        def connect(self):
            pass

        def send(self, data):
            received.put(data)

        def disconnect(self):
            pass

    with patch.object(sink.ejfat, "EjfatSender", RecordingSender):
        sink.run(args)


class SinkZmqTests(unittest.TestCase):
    def test_custom_port_receives_and_forwards_worker_payload(self):
        # Reserve an available port for this test instead of touching port 5555.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        parser = argparse.ArgumentParser()
        sink.add_arguments(parser)
        process_context = mp.get_context("spawn")
        received = process_context.Queue()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "ejfat_uri_processed.txt").write_text("unused-test-uri")
            args = parser.parse_args([
                "--credential-dir", directory, "--zmq-port", str(port),
            ])
            process = process_context.Process(
                target=run_sink_without_ejfat, args=(args, received),
            )
            process.start()
            context = zmq.Context()
            sender = context.socket(zmq.PUSH)
            sender.setsockopt(zmq.LINGER, 0)
            sender.setsockopt(zmq.SNDTIMEO, 5000)
            try:
                endpoint_file = Path(directory, "zmq_uri_sink.txt")
                deadline = time.monotonic() + 10
                while not endpoint_file.exists() and time.monotonic() < deadline:
                    self.assertTrue(process.is_alive(), "Sink exited during startup")
                    time.sleep(0.02)
                self.assertTrue(endpoint_file.exists(), "Sink did not advertise an endpoint")
                self.assertEqual(urlsplit(endpoint_file.read_text()).port, port)
                sender.connect(f"tcp://127.0.0.1:{port}")
                sender.send(b"worker-result")
                self.assertEqual(received.get(timeout=10), b"worker-result")
            finally:
                sender.close()
                context.term()
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=5)
                received.close()
                received.join_thread()


if __name__ == "__main__":
    unittest.main()
