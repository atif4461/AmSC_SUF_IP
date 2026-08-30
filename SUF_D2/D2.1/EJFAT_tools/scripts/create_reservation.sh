#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:18080}"
AUTH_HEADER="${AUTH_HEADER:-Bearer local-dev}"
NAME="${1:-local-demo-lb}"

curl -sS \
  -H "Authorization: ${AUTH_HEADER}" \
  -H 'Content-Type: application/json' \
  -X POST "${API_BASE}/movement/streaming/ejfat/control-plane-ip/loadbalancers" \
  -d "{\"name\":\"${NAME}\",\"sender_addresses\":[\"127.0.0.1\"],\"ip_family\":\"dual_stack\",\"strategy\":\"dynamic\"}" | tee reservation.json

echo
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("reservation.json").read_text())
Path("INSTANCE_URI").write_text(data["ejfat_uri"] + "\n")
PY

echo "Wrote reservation.json and INSTANCE_URI"
