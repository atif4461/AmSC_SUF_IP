from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from .control_plane import ControlPlane


@dataclass
class LBPacket:
    lb_id: str
    token: str
    sender_id: str
    receiver_id: str
    seq: int
    payload: str


class LBProtocol(asyncio.DatagramProtocol):
    def __init__(self, cp: ControlPlane, data_drop_rate: float) -> None:
        self.cp = cp
        self.drop_rate = max(0.0, min(1.0, data_drop_rate))
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.receivers: dict[tuple[str, str], tuple[str, int]] = {}
        self._rand = __import__("random")

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = json.loads(data.decode("utf-8"))
            msg_type = msg.get("type")
            if msg_type == "register_receiver":
                self._register_receiver(msg, addr)
                return
            if msg_type == "packet":
                self._forward_packet(msg)
                return
        except Exception:
            return

    def _register_receiver(self, msg: dict, addr: tuple[str, int]) -> None:
        lb_id = msg.get("lb_id", "")
        token = msg.get("token", "")
        receiver_id = msg.get("receiver_id", "")
        if not self.cp.validate_token(lb_id, token) or not receiver_id:
            return
        self.receivers[(lb_id, receiver_id)] = addr

    def _forward_packet(self, msg: dict) -> None:
        pkt = LBPacket(
            lb_id=msg.get("lb_id", ""),
            token=msg.get("token", ""),
            sender_id=msg.get("sender_id", ""),
            receiver_id=msg.get("receiver_id", ""),
            seq=int(msg.get("seq", 0)),
            payload=str(msg.get("payload", "")),
        )
        if not self.cp.validate_token(pkt.lb_id, pkt.token):
            return

        payload_bytes = len(pkt.payload.encode("utf-8"))
        dropped = 0
        if self._rand.random() < self.drop_rate:
            dropped = 1
            self.cp.update_tx(pkt.lb_id, pkt.sender_id, pkt.receiver_id, 1, payload_bytes, dropped)
            return

        receiver = self.receivers.get((pkt.lb_id, pkt.receiver_id))
        self.cp.update_tx(pkt.lb_id, pkt.sender_id, pkt.receiver_id, 1, payload_bytes, dropped)
        if receiver and self.transport:
            out = {
                "type": "packet",
                "lb_id": pkt.lb_id,
                "sender_id": pkt.sender_id,
                "receiver_id": pkt.receiver_id,
                "seq": pkt.seq,
                "payload": pkt.payload,
            }
            self.transport.sendto(json.dumps(out).encode("utf-8"), receiver)
            self.cp.update_rx(pkt.lb_id, pkt.sender_id, pkt.receiver_id, 1, payload_bytes)

