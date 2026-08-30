from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class IPFamily(str, Enum):
    DUAL_STACK = "dual_stack"
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class Strategy(str, Enum):
    DYNAMIC = "dynamic"
    STATIC = "static"
    EXPLICIT = "explicit"


@dataclass
class LoadBalancerConfig:
    name: str
    sender_addresses: List[str]
    until: Optional[datetime]
    ip_family: IPFamily
    strategy: Strategy
    api_url: str


@dataclass
class LoadBalancerReservation:
    lb_id: str
    token: str
    config: LoadBalancerConfig
    sync_ipv4_address: str
    sync_ipv6_address: str
    sync_udp_port: int
    data_ipv4_address: str
    data_ipv6_address: str
    data_min_port: int
    data_max_port: int
    fpga_lb_id: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StreamMetrics:
    sender_id: str
    receiver_id: str
    tx_packets: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    rx_bytes: int = 0
    dropped_packets: int = 0
    last_update_unix: float = 0.0


@dataclass
class ReservationMetrics:
    lb_id: str
    streams: Dict[str, StreamMetrics] = field(default_factory=dict)
    active_senders: int = 0
    active_receivers: int = 0

