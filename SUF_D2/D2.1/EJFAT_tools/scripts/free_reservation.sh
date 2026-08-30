#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:18080}"
AUTH_HEADER="${AUTH_HEADER:-Bearer local-dev}"
LB_ID="${1:-}"

if [[ -z "${LB_ID}" ]]; then
  if [[ -f reservation.json ]]; then
    LB_ID="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('reservation.json').read_text()).get('lb_id', ''))
PY
)"
  fi
fi

if [[ -z "${LB_ID}" || "${LB_ID}" == "null" ]]; then
  echo "Missing lb_id. Pass as arg or keep reservation.json in cwd."
  exit 1
fi

curl -sS \
  -H "Authorization: ${AUTH_HEADER}" \
  -X DELETE "${API_BASE}/movement/streaming/ejfat/control-plane-ip/loadbalancers/${LB_ID}"

echo
