
import argparse
import subprocess

from amsc import credentials

default_credential_dir="/testbed/home/nbrei/amsc_d2.1/"

def add_arguments(parser):
    parser.add_argument("--image", default="codecr.jlab.org/nbrei/amsc_expedition:latest", help="Container image to use for submitted jobs")
    parser.add_argument("--credential-dir", default=default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--worker-count", type=int, default=2, help="Number of worker jobs to launch")
    parser.add_argument("--include-source", action=argparse.BooleanOptionalAction, default=False, help="Launch source job (mainly for debugging)")


def run(args):
    print("Launching amsc_d2.1 workflow")
    print("  image:           ", args.image)
    print("  credential_dir:  ", args.credential_dir)
    print("  worker_count:    ", args.worker_count)
    print("  include_source:  ", args.include_source)

    #print("Registering new EJFAT instances...")
    #result = subprocess.run(
    #    ["sbatch", "--parsable", f"--export=ALL,IMAGE={image},CREDENTIAL_DIR={credential_dir}", "src/scripts/submit-reserver.sh"],
    #    capture_output=True, text=True, check=True
    #)
    #print(f"... Job id = ", result.stdout)

    print("Launching sink job...")
    result = subprocess.run(
        ["sbatch", "--parsable", f"--export=ALL,IMAGE={args.image},CREDENTIAL_DIR={args.credential_dir}", "src/scripts/submit-sink.sh"],
        capture_output=True, text=True, check=True
    )
    print(f"... Job id = ", result.stdout)


    print("Launching workers job...")
    result = subprocess.run(
        ["sbatch", "--parsable", f"--array=0-$(({args.worker_count-1}))", f"--export=ALL,IMAGE={args.image},CREDENTIAL_DIR={args.credential_dir}", "src/scripts/submit-workers.sh"],
        capture_output=True, text=True, check=True
    )
    print(f"... Job id = ", result.stdout)


    if args.include_source:
        print("Launching source job...")

        result = subprocess.run(
            ["sbatch", "--parsable", f"--export=ALL,IMAGE={args.image_name},CREDENTIAL_DIR={args.credential_dir},SOURCE_FILE={args.source_file}", "src/scripts/submit-source.sh"],
            capture_output=True, text=True, check=True
        )

        print(f"... Job id = ", result.stdout)



