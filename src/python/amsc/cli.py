
import argparse
from amsc import source_ejfat,worker_ejfat,sink,ejfat_admin


def main(argv=None):

    parser = argparse.ArgumentParser(prog="amsc", description="A unified interface for Nathan's AmSC adventures")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # register-ejfat-instance
    reg_parser = subparsers.add_parser("reserve-ejfat", help="Reserve an EJFAT load balancer instance")
    ejfat_admin.add_arguments(reg_parser)
    reg_parser.set_defaults(func=ejfat_admin.run)

    # run-source
    source_parser = subparsers.add_parser("run-source", help="Run source process")
    source_ejfat.add_arguments(source_parser)
    source_parser.set_defaults(func=source_ejfat.run)

    # run-worker
    worker_parser = subparsers.add_parser("run-worker", help="Run worker process")
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

