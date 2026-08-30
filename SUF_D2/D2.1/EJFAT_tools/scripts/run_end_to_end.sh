#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:18080}"
AUTH_HEADER="${AUTH_HEADER:-Bearer local-dev}"
HOST="${HOST:-127.0.0.1}"
DATA_PORT="${DATA_PORT:-18020}"

if [[ ! -f reservation.json ]]; then
  scripts/create_reservation.sh "local-demo-lb"
fi

LB_ID="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('reservation.json').read_text()).get('lb_id', ''))
PY
)"
TOKEN="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('reservation.json').read_text()).get('token', ''))
PY
)"

if [[ -z "${LB_ID}" || -z "${TOKEN}" ]]; then
  scripts/create_reservation.sh "local-demo-lb"
  LB_ID="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('reservation.json').read_text()).get('lb_id', ''))
PY
)"
  TOKEN="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('reservation.json').read_text()).get('token', ''))
PY
)"
fi

HTTP_CODE="$(curl -sS -o /dev/null -w "%{http_code}" -H "Authorization: ${AUTH_HEADER}" "${API_BASE}/movement/streaming/ejfat/control-plane-ip/loadbalancers/${LB_ID}")"
if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "Existing reservation ${LB_ID} is stale (HTTP ${HTTP_CODE}); creating a new reservation."
  scripts/create_reservation.sh "local-demo-lb"
  LB_ID="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('reservation.json').read_text()).get('lb_id', ''))
PY
)"
  TOKEN="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path('reservation.json').read_text()).get('token', ''))
PY
)"
fi

python3 tools/receiver.py --host "${HOST}" --data-port "${DATA_PORT}" --listen-port 18100 --lb-id "${LB_ID}" --token "${TOKEN}" --receiver-id receiver-1 --duration 12 > receiver.log 2>&1 &
RX_PID=$!

python3 tools/monitor_tui.py --api-base "${API_BASE}" --lb-id "${LB_ID}" --auth "${AUTH_HEADER}" --duration 10 &
MON_PID=$!

sleep 1
python3 tools/sender.py --host "${HOST}" --data-port "${DATA_PORT}" --lb-id "${LB_ID}" --token "${TOKEN}" --sender-id sender-1 --receiver-id receiver-1 --rate 1500000 --count 1000000 --payload-bytes 8192 > sender.log 2>&1

wait "${RX_PID}" || true
wait "${MON_PID}" || true

echo "=== sender.log ==="
cat sender.log

echo "=== receiver.log ==="
cat receiver.log

echo "=== metrics snapshot ==="
curl -sS -H "Authorization: ${AUTH_HEADER}" "${API_BASE}/movement/streaming/ejfat/control-plane-ip/loadbalancers/${LB_ID}/metrics" | python3 -m json.tool
