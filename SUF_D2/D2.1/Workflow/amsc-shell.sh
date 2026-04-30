#!/bin/bash

set -euo pipefail

podman run -it --rm \
    --env EJFAT_URI \
    --network host \
    --userns=keep-id \
    --security-opt label=disable \
    -v "$PWD:$PWD:rw" \
    -w "$PWD" \
    --entrypoint /bin/bash \
    codecr.jlab.org/nbrei/amsc_expedition:latest


