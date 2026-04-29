
#!/usr/bin/env bash
#SBATCH --job-name=amsc-d2.1-demo-worker
#SBATCH --ntasks=1
#SBATCH --output=logs/worker-%A-%a.out     # %A = array job ID, %a = task index
#SBATCH --error=logs/worker-%A-%a.err

set -euo pipefail

# SLURM_ARRAY_TASK_ID is your worker index (0..N-1)
# SLURM_JOB_NODELIST gives the node this task landed on

podman run \
    --rm \
    --network host \
    --userns=keep-id \
    --security-opt label=disable \
    --volume "$PWD:$PWD:rw" \
    --volume "${CREDENTIAL_DIR}:/cred:rw" \
    --workdir "$PWD" \
    ${IMAGE}
    amsc run-worker --name=worker_${SLURM_ARRAY_TASK_ID} --credential-dir=/cred



