
import argparse
from amsc import reserver,source,worker,sink,launcher,server,unreserver,loopback,receiver


def main(argv=None):

    parser = argparse.ArgumentParser(prog="amsc", description="A unified interface for Nathan's AmSC adventures")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # launch
    launch_parser = subparsers.add_parser("launcher", help="Launch entire workflow on a SLURM cluster")
    launcher.add_arguments(launch_parser)
    launch_parser.set_defaults(func=launcher.run)

    # server
    server_parser = subparsers.add_parser("server", help="REST API for managing workflows on a SLURM cluster")
    server.add_arguments(server_parser)
    server_parser.set_defaults(func=server.run)

    # reserve
    res_parser = subparsers.add_parser("reserve", help="Reserve an EJFAT load balancer instance")
    reserver.add_arguments(res_parser)
    res_parser.set_defaults(func=reserver.run)

    # unreserve
    unres_parser = subparsers.add_parser("unreserve", help="Unreserve an EJFAT load balancer instance")
    unreserver.add_arguments(unres_parser)
    unres_parser.set_defaults(func=unreserver.run)

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

    # run-loopback
    loopback_parser = subparsers.add_parser("run-loopback", help="Run EJFAT loopback (sender + receiver)")
    loopback.add_arguments(loopback_parser)
    loopback_parser.set_defaults(func=loopback.run)

    # parse_args defaults to sys.argv when argv=None
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        parser.exit(1)

    return args.func(args)

if __name__ == '__main__':
    main()

