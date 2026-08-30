#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:18080}"
AUTH_HEADER="${AUTH_HEADER:-Bearer local-dev}"
HOST="${HOST:-127.0.0.1}"
DATA_PORT="${DATA_PORT:-18020}"
SENDERS="${SENDERS:-4}"
COUNT_PER_SENDER="${COUNT_PER_SENDER:-6000}"
RATE_PER_SENDER="${RATE_PER_SENDER:-1200}"
PAYLOAD_BYTES="${PAYLOAD_BYTES:-512}"
DURATION="${DURATION:-15}"

if [[ ! -f reservation.json ]]; then
  scripts/create_reservation.sh "local-multi-sender"
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
  scripts/create_reservation.sh "local-multi-sender"
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
  scripts/create_reservation.sh "local-multi-sender"
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

rm -f sender_*.log receiver_multi.log

python3 tools/receiver.py \
  --host "${HOST}" \
  --data-port "${DATA_PORT}" \
  --listen-port 18100 \
  --lb-id "${LB_ID}" \
  --token "${TOKEN}" \
  --receiver-id receiver-1 \
  --duration "${DURATION}" > receiver_multi.log 2>&1 &
RX_PID=$!

python3 tools/monitor_tui.py --api-base "${API_BASE}" --lb-id "${LB_ID}" --auth "${AUTH_HEADER}" --duration "$((DURATION-2))" &
MON_PID=$!

sleep 1

SENDER_PIDS=()
for i in $(seq 1 "${SENDERS}"); do
  python3 tools/sender.py \
    --host "${HOST}" \
    --data-port "${DATA_PORT}" \
    --lb-id "${LB_ID}" \
    --token "${TOKEN}" \
    --sender-id "sender-${i}" \
    --receiver-id receiver-1 \
    --rate "${RATE_PER_SENDER}" \
    --count "${COUNT_PER_SENDER}" \
    --payload-bytes "${PAYLOAD_BYTES}" > "sender_${i}.log" 2>&1 &
  SENDER_PIDS+=("$!")
done

for pid in "${SENDER_PIDS[@]}"; do
  wait "${pid}" || true
done

wait "${RX_PID}" || true
wait "${MON_PID}" || true

echo "=== sender logs summary ==="
for i in $(seq 1 "${SENDERS}"); do
  echo "--- sender_${i}.log ---"
  cat "sender_${i}.log"
done

echo "=== receiver_multi.log ==="
cat receiver_multi.log

echo "=== metrics snapshot ==="
curl -sS -H "Authorization: ${AUTH_HEADER}" "${API_BASE}/movement/streaming/ejfat/control-plane-ip/loadbalancers/${LB_ID}/metrics" | python3 -m json.tool
