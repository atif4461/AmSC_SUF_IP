from __future__ import annotations

import secrets
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional

from .models import (
    IPFamily,
    LoadBalancerConfig,
    LoadBalancerReservation,
    ReservationMetrics,
    Strategy,
    StreamMetrics,
)
from .runtime import SharedState


class ControlPlane:
    def __init__(self, public_host: str, api_port: int, sync_port: int, data_min_port: int, data_max_port: int) -> None:
        self._lock = Lock()
        self._reservations: Dict[str, LoadBalancerReservation] = {}
        self._metrics: Dict[str, ReservationMetrics] = {}
        self.public_host = public_host
        self.api_port = api_port
        self.sync_port = sync_port
        self.data_min_port = data_min_port
        self.data_max_port = data_max_port

    def create_reservation(
        self,
        *,
        name: str,
        sender_addresses: list[str],
        until: Optional[datetime],
        ip_family: IPFamily,
        strategy: Strategy,
        api_url: str,
    ) -> LoadBalancerReservation:
        with self._lock:
            lb_id = str(uuid.uuid4())
            token = secrets.token_urlsafe(24)
            config = LoadBalancerConfig(
                name=name,
                sender_addresses=sender_addresses,
                until=until,
                ip_family=ip_family,
                strategy=strategy,
                api_url=api_url,
            )
            reservation = LoadBalancerReservation(
                lb_id=lb_id,
                token=token,
                config=config,
                sync_ipv4_address=self.public_host,
                sync_ipv6_address="::1",
                sync_udp_port=self.sync_port,
                data_ipv4_address=self.public_host,
                data_ipv6_address="::1",
                data_min_port=self.data_min_port,
                data_max_port=self.data_max_port,
                fpga_lb_id=int.from_bytes(secrets.token_bytes(2), "big"),
            )
            self._reservations[lb_id] = reservation
            self._metrics[lb_id] = ReservationMetrics(lb_id=lb_id)
            self._sync_reservations_locked()
            return reservation

    def get_reservation(self, lb_id: str) -> Optional[LoadBalancerReservation]:
        with self._lock:
            self._expire_locked()
            return self._reservations.get(lb_id)

    def free_reservation(self, lb_id: str) -> bool:
        with self._lock:
            existed = lb_id in self._reservations
            self._reservations.pop(lb_id, None)
            self._metrics.pop(lb_id, None)
            self._sync_reservations_locked()
            return existed

    def validate_token(self, lb_id: str, token: str) -> bool:
        with self._lock:
            self._expire_locked()
            res = self._reservations.get(lb_id)
            return bool(res and secrets.compare_digest(res.token, token))

    def update_tx(self, lb_id: str, sender_id: str, receiver_id: str, packets: int, bytes_count: int, dropped: int) -> None:
        with self._lock:
            metrics = self._metrics.get(lb_id)
            if not metrics:
                return
            key = f"{sender_id}:{receiver_id}"
            stream = metrics.streams.setdefault(key, StreamMetrics(sender_id=sender_id, receiver_id=receiver_id))
            stream.tx_packets += packets
            stream.tx_bytes += bytes_count
            stream.dropped_packets += dropped
            stream.last_update_unix = datetime.now(timezone.utc).timestamp()
            metrics.active_senders = len({s.sender_id for s in metrics.streams.values()})

    def update_rx(self, lb_id: str, sender_id: str, receiver_id: str, packets: int, bytes_count: int) -> None:
        with self._lock:
            metrics = self._metrics.get(lb_id)
            if not metrics:
                return
            key = f"{sender_id}:{receiver_id}"
            stream = metrics.streams.setdefault(key, StreamMetrics(sender_id=sender_id, receiver_id=receiver_id))
            stream.rx_packets += packets
            stream.rx_bytes += bytes_count
            stream.last_update_unix = datetime.now(timezone.utc).timestamp()
            metrics.active_receivers = len({s.receiver_id for s in metrics.streams.values()})

    def get_metrics(self, lb_id: str) -> Optional[dict]:
        with self._lock:
            self._expire_locked()
            all_metrics = SharedState.read_metrics()
            metrics_doc = all_metrics.get(lb_id)
            if metrics_doc is not None:
                return {
                    "lb_id": lb_id,
                    "active_senders": int(metrics_doc.get("active_senders", 0)),
                    "active_receivers": int(metrics_doc.get("active_receivers", 0)),
                    "streams": metrics_doc.get("streams", []),
                    "workers": all_metrics.get("workers", []),
                }

            metrics = self._metrics.get(lb_id)
            if not metrics:
                return None
            streams = []
            for stream in metrics.streams.values():
                loss_pct = 0.0
                if stream.tx_packets > 0:
                    loss_pct = ((stream.tx_packets - stream.rx_packets) / stream.tx_packets) * 100.0
                streams.append(
                    {
                        **asdict(stream),
                        "packet_loss_pct": round(max(loss_pct, 0.0), 3),
                    }
                )

            return {
                "lb_id": lb_id,
                "active_senders": metrics.active_senders,
                "active_receivers": metrics.active_receivers,
                "streams": streams,
            }

    def list_reservations(self) -> list[LoadBalancerReservation]:
        with self._lock:
            self._expire_locked()
            return list(self._reservations.values())

    def _expire_locked(self) -> None:
        now = datetime.now(timezone.utc)
        to_delete = []
        for lb_id, reservation in self._reservations.items():
            if reservation.config.until and reservation.config.until <= now:
                to_delete.append(lb_id)
        for lb_id in to_delete:
            self._reservations.pop(lb_id, None)
            self._metrics.pop(lb_id, None)
        if to_delete:
            self._sync_reservations_locked()

    def _sync_reservations_locked(self) -> None:
        items = []
        for reservation in self._reservations.values():
            items.append(
                {
                    "lb_id": reservation.lb_id,
                    "token": reservation.token,
                }
            )
        SharedState.write_reservations(items)
