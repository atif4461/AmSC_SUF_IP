#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time


class ReceiverProtocol(asyncio.DatagramProtocol):
    def __init__(self, lb_id: str, token: str, receiver_id: str, stop_after: float) -> None:
        self.lb_id = lb_id
        self.token = token
        self.receiver_id = receiver_id
        self.stop_after = stop_after
        self.transport: asyncio.DatagramTransport | None = None
        self.received = 0
        self.start = 0.0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        self.start = time.time()
        self.send_register()

    def send_register(self) -> None:
        if not self.transport:
            return
        register_msg = {
            "type": "register_receiver",
            "lb_id": self.lb_id,
            "token": self.token,
            "receiver_id": self.receiver_id,
        }
        self.transport.sendto(json.dumps(register_msg).encode("utf-8"))

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = json.loads(data.decode("utf-8"))
            if msg.get("type") == "packet":
                self.received += 1
        except Exception:
            pass


async def run_receiver(args: argparse.Namespace) -> None:
    loop = asyncio.get_running_loop()
    _, proto = await loop.create_datagram_endpoint(
        lambda: ReceiverProtocol(args.lb_id, args.token, args.receiver_id, args.duration),
        local_addr=("0.0.0.0", args.listen_port),
        remote_addr=(args.host, args.data_port),
    )

    deadline = time.time() + args.duration
    while time.time() < deadline:
        proto.send_register()
        await asyncio.sleep(0.5)

    elapsed = max(0.0001, time.time() - proto.start)
    rate = proto.received / elapsed
    print(f"receiver_complete packets={proto.received} elapsed_s={elapsed:.3f} pkt_rate={rate:.2f}")
    if proto.transport:
        proto.transport.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CPU EJFAT emulator receiver")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--data-port", type=int, default=18020)
    p.add_argument("--listen-port", type=int, default=18100)
    p.add_argument("--lb-id", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--receiver-id", default="receiver-1")
    p.add_argument("--duration", type=float, default=10.0)
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run_receiver(parse_args()))
