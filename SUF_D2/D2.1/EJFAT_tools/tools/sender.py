#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time


class SenderProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]


async def run_sender(args: argparse.Namespace) -> None:
    loop = asyncio.get_running_loop()
    _, protocol = await loop.create_datagram_endpoint(
        SenderProtocol,
        remote_addr=(args.host, args.data_port),
    )

    assert protocol.transport is not None
    interval = 1.0 / args.rate if args.rate > 0 else 0.0
    payload = "x" * max(1, args.payload_bytes)

    sent = 0
    start = time.time()
    for i in range(args.count):
        msg = {
            "type": "packet",
            "lb_id": args.lb_id,
            "token": args.token,
            "sender_id": args.sender_id,
            "receiver_id": args.receiver_id,
            "seq": i,
            "payload": payload,
        }
        protocol.transport.sendto(json.dumps(msg).encode("utf-8"))
        sent += 1
        if interval > 0:
            await asyncio.sleep(interval)

    elapsed = max(0.0001, time.time() - start)
    rate = sent / elapsed
    print(f"sender_complete packets={sent} elapsed_s={elapsed:.3f} pkt_rate={rate:.2f}")
    protocol.transport.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CPU EJFAT emulator sender")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--data-port", type=int, default=18020)
    p.add_argument("--lb-id", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--sender-id", default="sender-1")
    p.add_argument("--receiver-id", default="receiver-1")
    p.add_argument("--rate", type=float, default=1000.0, help="Packets per second")
    p.add_argument("--count", type=int, default=5000)
    p.add_argument("--payload-bytes", type=int, default=512)
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run_sender(parse_args()))
