
import argparse
from amsc import source,worker,sink
from sys import argv


def main(argv=None):

    print("This is supposed to show")
    parser = argparse.ArgumentParser(prog="amsc", description="A unified interface for Nathan's AmSC adventures")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # run-source
    source_parser = subparsers.add_parser("run-source", help="Run source process")
    source.add_arguments(source_parser)
    source_parser.set_defaults(func=source.run)

    # run-worker
    worker_parser = subparsers.add_parser("run-worker", help="Run worker process")
    worker.add_arguments(worker_parser)
    worker_parser.set_defaults(func=worker.run)

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

