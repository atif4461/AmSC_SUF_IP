#!/usr/bin/env bash
#SBATCH --job-name=amsc-d2.1-demo-source
#SBATCH --ntasks=1
#SBATCH --output=logs/sink-%j.out
#SBATCH --error=logs/sink-%j.err

set -euo pipefail

podman run \
    --rm \
    --network host \
    --userns=keep-id \
    --security-opt label=disable \
    --volume "$PWD:$PWD:rw" \
    --volume "${CREDENTIAL_DIR}:/cred:rw" \
    --workdir "$PWD" \
    ${IMAGE}
    amsc run-source $SOURCE_FILE


