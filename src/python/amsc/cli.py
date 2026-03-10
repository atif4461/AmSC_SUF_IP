
import argparse
from amsc import source_ejfat,source_zmq,worker_ejfat,worker_zmq,sink


def main(argv=None):

    parser = argparse.ArgumentParser(prog="amsc", description="A unified interface for Nathan's AmSC adventures")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # run-zmq-source
    source_parser = subparsers.add_parser("run-zmq-source", help="Run source process over ZMQ")
    source_zmq.add_arguments(source_parser)
    source_parser.set_defaults(func=source_zmq.run)

    # run-ejfat-source
    source_parser = subparsers.add_parser("run-ejfat-source", help="Run source process over EJFAT")
    source_ejfat.add_arguments(source_parser)
    source_parser.set_defaults(func=source_ejfat.run)

    # run-zmq-worker
    worker_parser = subparsers.add_parser("run-zmq-worker", help="Run worker process over ZMQ")
    worker_zmq.add_arguments(worker_parser)
    worker_parser.set_defaults(func=worker_zmq.run)

    # run-ejfat-worker
    worker_parser = subparsers.add_parser("run-ejfat-worker", help="Run worker process over EJFAT")
    worker_ejfat.add_arguments(worker_parser)
    worker_parser.set_defaults(func=worker_ejfat.run)

    # run-sink
    sink_parser = subparsers.add_parser("run-sink", help="Run sink process")
    sink.add_arguments(sink_parser)
    sink_parser.set_defaults(func=sink.run)

    # parse_args defaults to sys.argv when argv=None
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        parser.exit(1)

    return args.func(args)

if __name__ == '__main__':
    main()

