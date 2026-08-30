# Local CPU EJFAT Emulator for AmSC Demo Development

This workspace now contains a local, CPU-based EJFAT-like development environment with:

- REST API compatible path structure with AmSC demo EJFAT endpoints
- Emulated EJFAT load balancer data path over UDP implemented in C++
- EJFAT-style control plane reservation lifecycle
- Sender/receiver load test tools
- Live TUI monitoring from control-plane metrics

It is intended for offline development of reservation + streaming software that can later target real ESNet/JLab EJFAT infrastructure.

## What Is Implemented

Architecture summary:

- Python FastAPI service provides reservation/control-plane REST API
- Native C++ sidecar handles UDP data-plane forwarding and stream counters
- Shared state files bridge control plane to sidecar (`reservations.json`, `metrics.json`)

REST API paths:

- `GET /health`
- `GET /movement/streaming/ejfat/health`
- `GET /movement/streaming/ejfat/version` (requires `Authorization` header)
- `POST /movement/streaming/ejfat/control-plane-ip/loadbalancers` (requires `Authorization`)
- `GET /movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}` (requires `Authorization`)
- `DELETE /movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}` (requires `Authorization`)
- `GET /movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}/metrics` (requires `Authorization`)

The create response includes fields aligned with the AmSC demo schema, including:

- `token`, `lb_id`
- `sync_*`, `data_*`
- `fpga_lb_id` (emulated ID)
- `strategy`
- `ejfat_uri`

Data plane behavior:

- Receiver registers to LB with reservation token
- Sender emits packet stream to LB
- C++ LB validates reservation token, forwards packets, tracks tx/rx/loss counters
- Optional drop emulation via `EJFAT_EMULATED_DROP_RATE`

## Quick Start (Local Python)

1. Create environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start emulator (API + UDP LB):

```bash
scripts/build_cpp_lb.sh
PYTHONPATH=src python -m ejfat_emulator.main
```

3. In another terminal, create reservation:

```bash
source .venv/bin/activate
scripts/create_reservation.sh demo-lb
```

4. Run end-to-end test with live monitor:

```bash
source .venv/bin/activate
scripts/run_end_to_end.sh
```

Optional: run a multi-sender load test (useful for observing worker distribution):

```bash
source .venv/bin/activate
SENDERS=4 COUNT_PER_SENDER=6000 RATE_PER_SENDER=1200 scripts/run_multi_sender_test.sh
```

Optional: run an automated stress sweep (workers x rates) and generate CSV + plot:

```bash
source .venv/bin/activate
scripts/run_stress_sweep.sh
```

Custom sweep example:

```bash
scripts/run_stress_sweep.sh \
	--workers 1,2,4,8 \
	--rates 2000,5000,10000,20000 \
	--senders 8 \
	--count-per-sender 20000 \
	--payload-bytes 1024
```

Outputs are written to:

- `artifacts/stress_sweep.csv`
- `artifacts/stress_sweep.json`
- `artifacts/stress_sweep_knees.json`
- `artifacts/stress_sweep.png`
- `artifacts/stress_sweep_goodput.png`
- `artifacts/stress_sweep_combined.png`

Knee detection:

- The sweep automatically marks each worker-count knee as the first point where loss exceeds a threshold (default `1.0%`).
- Configure threshold with `--knee-loss-threshold`.

5. Free reservation:

```bash
source .venv/bin/activate
scripts/free_reservation.sh
```

## Quick Start (Docker)

Build and run container:

```bash
docker compose up --build
```

The Docker image builds and starts the C++ data-plane binary automatically.

This exposes:

- `18080/tcp` API
- `18020/udp` data plane
- `19020/udp` sync port (control-plane metadata)

Then run scripts from host (local Python needed for tools):

```bash
source .venv/bin/activate
scripts/create_reservation.sh demo-lb
scripts/run_end_to_end.sh
scripts/free_reservation.sh
```

## Testing and Monitoring Tools

- `tools/sender.py`: packet generator
- `tools/receiver.py`: receiver registration + packet sink
- `tools/monitor_tui.py`: live TUI with stream metrics
- `scripts/run_multi_sender_test.sh`: starts N concurrent senders for worker-distribution tests
- `scripts/run_stress_sweep.sh`: runs matrix stress tests and writes loss-vs-load, goodput-vs-load, and combined dual-axis artifacts

Example monitor call:

```bash
python3 tools/monitor_tui.py --api-base http://127.0.0.1:18080 --lb-id <lb_id> --auth "Bearer local-dev" --duration 30
```

## Environment Variables

- `EJFAT_PUBLIC_HOST` (default `127.0.0.1`)
- `EJFAT_API_PORT` (default `18080`)
- `EJFAT_SYNC_PORT` (default `19020`)
- `EJFAT_DATA_PORT` (default `18020`)
- `EJFAT_DATA_MIN_PORT` (default `18020`)
- `EJFAT_DATA_MAX_PORT` (default `18020`)
- `EJFAT_EMULATED_DROP_RATE` (default `0.0`)
- `EJFAT_DATA_WORKERS` (default `2`)
- `EJFAT_METRICS_FLUSH_INTERVAL_MS` (default `100`)
- `EJFAT_PIN_WORKERS` (default `false`, Linux-only affinity pinning)
- `EJFAT_PIN_BASE_CPU` (default `0`, Linux-only starting CPU index)

Metrics behavior:

- Metrics are flushed on a short interval and on frequent packet boundaries.
- This keeps snapshot counters near real-time while avoiding per-packet disk writes.
- Metrics include optional per-worker counters under top-level `workers`.
- Worker counters include byte counters (`rx_datagram_bytes`, `forwarded_bytes`) for Mbps calculations.
- Ingestion now uses explicit round-robin dispatch to workers so local tests spread work beyond worker-0.

## Notes and Limits

- This is a CPU emulator, not FPGA accelerated.
- API compatibility focuses on EJFAT reservation and control-plane development paths.
- Authentication is intentionally lightweight for local use (`Authorization` header presence check).
- Transport and metrics are sufficient for functional integration development and local validation.
