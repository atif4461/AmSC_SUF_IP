#!/usr/bin/env bash
set -euo pipefail

workflow_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(dirname -- "$workflow_dir")"
state_dir="$workflow_dir/.apptainer"
image="$state_dir/e2sar-0.4.0rc1.sif"
credential_dir="${AMSC_CREDENTIAL_DIR:-$state_dir/credentials}"

usage() {
    cat <<'EOF'
Usage: bash Workflow/amsc-apptainer.sh COMMAND [ARGS...]

  setup                 Download E2SAR 0.4.0rc1 and install Python dependencies.
  check                 Verify imports and workflow CLI in the saved environment.
  shell                 Open a shell with the saved Python environment activated.
  sink [ARGS...]        Run the sink using the saved environment and credentials.
  worker [ARGS...]      Run workers using the saved environment and credentials.
  test-sender [ARGS...] Send generated Arrow batches for a connectivity test.
  source FILE [ARGS...] Run the source with a local HDDM file and amsc options.

State is saved in Workflow/.apptainer/ (ignored by Git).
Put the two URI files in Workflow/.apptainer/credentials/:
  ejfat_uri_raw.txt
  ejfat_uri_processed.txt
Override that directory with AMSC_CREDENTIAL_DIR if needed.
Keep the host monitor running at tcp://127.0.0.1:5557.
EOF
}

action="${1:-help}"
if [[ "$action" == help || "$action" == --help || "$action" == -h ]]; then
    usage
    exit 0
fi
shift
case "$action" in
    setup|check|shell|source|sink|worker|test-sender) ;;
    *) usage >&2; exit 2 ;;
esac

command -v apptainer >/dev/null || { echo 'apptainer is not on PATH.' >&2; exit 1; }
mkdir -p "$state_dir" "$credential_dir"
chmod 700 "$credential_dir"
credential_dir="$(cd -- "$credential_dir" && pwd)"

container_args=(
    exec --cleanenv --no-home
    --bind "$repo_dir:/work:ro"
    --bind "$state_dir:/env:rw"
    --bind "$credential_dir:/cred:rw"
    --pwd /work
    --env PYTHONPATH=/work/Workflow/src/python:/e2sar-install/lib/python3/dist-packages
    --env PYTHONNOUSERSITE=1
    --env PYTHONDONTWRITEBYTECODE=1
)

check_environment() {
    apptainer "${container_args[@]}" "$image" /env/venv/bin/python -c \
        'import e2sar_py, pyarrow, zmq, numpy, pandas, flask; from gluex import hddm_r; print("Imports OK"); print("E2SAR:", e2sar_py.__file__); print("HDDM:", hddm_r.__file__)'
    apptainer "${container_args[@]}" "$image" /env/venv/bin/python -m amsc.cli run-source --help
}

if [[ "$action" == setup ]]; then
    uv_binary="$(command -v uv)" || { echo 'uv is needed on the host for setup.' >&2; exit 1; }
    uv_binary="$(readlink -f -- "$uv_binary")"
    mkdir -p "$state_dir/cache"
    export APPTAINER_CACHEDIR="$state_dir/cache"
    if [[ ! -f "$image" ]]; then
        apptainer pull "$image" docker://docker.io/ibaldin/e2sar:0.4.0rc1
    fi
    # uv creates the environment without needing ensurepip or apt-get.
    setup_args=("${container_args[@]}" --bind "$uv_binary:/tools/uv:ro")
    apptainer "${setup_args[@]}" "$image" python3 -c \
        'import e2sar_py; print("E2SAR:", e2sar_py.__file__)'
    if [[ ! -x "$state_dir/venv/bin/python" ]]; then
        apptainer "${setup_args[@]}" "$image" /tools/uv venv \
            --cache-dir /env/uv-cache \
            --python /usr/bin/python3 --no-managed-python --system-site-packages /env/venv
    fi
    apptainer "${setup_args[@]}" "$image" /tools/uv pip install \
        --cache-dir /env/uv-cache --python /env/venv/bin/python \
        -r /work/Monitor/requirements.txt
    cat > "$state_dir/activate.sh" <<'EOF'
source /env/venv/bin/activate
export PYTHONPATH=/work/Workflow/src/python:/e2sar-install/lib/python3/dist-packages
EOF
    check_environment
    echo "Setup saved in $state_dir"
    exit 0
fi

if [[ ! -f "$image" || ! -x "$state_dir/venv/bin/python" ]]; then
    echo 'Run setup first: bash Workflow/amsc-apptainer.sh setup' >&2
    exit 1
fi

case "$action" in
    check) check_environment ;;
    sink|worker)
        if [[ "$action" == sink ]]; then
            required_uri=ejfat_uri_processed.txt
        else
            required_uri=ejfat_uri_raw.txt
        fi
        [[ -s "$credential_dir/$required_uri" ]] || {
            echo "Missing URI file: $credential_dir/$required_uri" >&2
            exit 1
        }
        exec apptainer "${container_args[@]}" "$image" \
            /env/venv/bin/python -u -m amsc.cli "run-$action" \
            --credential-dir=/cred "$@"
        ;;
    test-sender)
        exec apptainer "${container_args[@]}" "$image" \
            /env/venv/bin/python -u /work/Workflow/src/scripts/test-ejfat-sender.py \
            --credential-dir=/cred "$@"
        ;;
    shell)
        # Activate only the container environment, without host shell startup files.
        exec apptainer "${container_args[@]}" "$image" /bin/bash --noprofile --rcfile \
            /env/activate.sh
        ;;
    source)
        [[ $# -ge 1 ]] || { echo 'source requires a local HDDM filename.' >&2; exit 2; }
        [[ -r "$1" && -f "$1" ]] || { echo "Cannot read input file: $1" >&2; exit 1; }
        data_file="$(readlink -f -- "$1")"
        shift
        for filename in ejfat_uri_raw.txt ejfat_uri_processed.txt; do
            [[ -s "$credential_dir/$filename" ]] || {
                echo "Missing URI file: $credential_dir/$filename" >&2
                exit 1
            }
        done
        exec apptainer "${container_args[@]}" \
            --bind "$(dirname -- "$data_file"):/input:ro" "$image" \
            /env/venv/bin/python -u -m amsc.cli run-source \
            "/input/$(basename -- "$data_file")" --credential-dir=/cred "$@"
        ;;
esac
