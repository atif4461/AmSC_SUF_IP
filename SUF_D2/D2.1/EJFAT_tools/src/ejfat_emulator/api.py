from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .control_plane import ControlPlane
from .models import IPFamily, Strategy


PUBLIC_HOST = os.getenv("EJFAT_PUBLIC_HOST", "127.0.0.1")
API_PORT = int(os.getenv("EJFAT_API_PORT", "18080"))
SYNC_PORT = int(os.getenv("EJFAT_SYNC_PORT", "19020"))
DATA_PORT = int(os.getenv("EJFAT_DATA_PORT", "18020"))
DATA_MIN_PORT = int(os.getenv("EJFAT_DATA_MIN_PORT", str(DATA_PORT)))
DATA_MAX_PORT = int(os.getenv("EJFAT_DATA_MAX_PORT", str(DATA_PORT)))


control_plane = ControlPlane(
    public_host=PUBLIC_HOST,
    api_port=API_PORT,
    sync_port=SYNC_PORT,
    data_min_port=DATA_MIN_PORT,
    data_max_port=DATA_MAX_PORT,
)


class EJfatCreateLoadBalancerRequest(BaseModel):
    name: str = Field(description="Human-readable name for the load balancer instance")
    sender_addresses: list[str] = Field(description="List of allowed sender IP addresses (IPv4 or IPv6)")
    until: Optional[datetime] = Field(default=None)
    ip_family: Optional[IPFamily] = Field(default=IPFamily.DUAL_STACK)
    strategy: Optional[Strategy] = Field(default=Strategy.DYNAMIC)
    api_url: Optional[str] = Field(default="https://ejfat-lb.es.net:18072/api/v1")


class EJfatLoadBalancerResponse(BaseModel):
    token: str
    lb_id: str
    sync_ipv4_address: str
    sync_ipv6_address: str
    sync_udp_port: int
    data_ipv4_address: str
    data_ipv6_address: str
    data_min_port: int
    data_max_port: int
    fpga_lb_id: int
    strategy: Strategy
    ejfat_uri: str


def _auth_header_ok(authorization: Optional[str] = Header(default=None)) -> bool:
    return authorization is not None and len(authorization.strip()) > 0


def _require_auth(authorization_ok: bool = Depends(_auth_header_ok)) -> None:
    if not authorization_ok:
        raise HTTPException(status_code=401, detail="Authorization header required")


app = FastAPI(title="Local AmSC EJFAT Emulator", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/movement/streaming/ejfat/health")
def ejfat_health() -> dict:
    return {"status": "healthy", "component": "ejfat-emulator"}


@app.get("/movement/streaming/ejfat/version")
def ejfat_version(_: None = Depends(_require_auth)) -> dict:
    return {"version": "local-cpu-emulator-0.1.0"}


@app.post("/movement/streaming/ejfat/control-plane-ip/loadbalancers", response_model=EJfatLoadBalancerResponse)
def create_load_balancer(req: EJfatCreateLoadBalancerRequest, _: None = Depends(_require_auth)) -> EJfatLoadBalancerResponse:
    reservation = control_plane.create_reservation(
        name=req.name,
        sender_addresses=req.sender_addresses,
        until=req.until,
        ip_family=req.ip_family or IPFamily.DUAL_STACK,
        strategy=req.strategy or Strategy.DYNAMIC,
        api_url=req.api_url or "https://ejfat-lb.es.net:18072/api/v1",
    )
    ejfat_uri = (
        f"ejfats://{reservation.token}@{PUBLIC_HOST}:{API_PORT}/lb/{reservation.lb_id}"
        f"?sync={reservation.sync_ipv4_address}:{reservation.sync_udp_port}"
        f"&data={reservation.data_ipv4_address}:{DATA_PORT}"
    )
    return EJfatLoadBalancerResponse(
        token=reservation.token,
        lb_id=reservation.lb_id,
        sync_ipv4_address=reservation.sync_ipv4_address,
        sync_ipv6_address=reservation.sync_ipv6_address,
        sync_udp_port=reservation.sync_udp_port,
        data_ipv4_address=reservation.data_ipv4_address,
        data_ipv6_address=reservation.data_ipv6_address,
        data_min_port=reservation.data_min_port,
        data_max_port=reservation.data_max_port,
        fpga_lb_id=reservation.fpga_lb_id,
        strategy=reservation.config.strategy,
        ejfat_uri=ejfat_uri,
    )


@app.get("/movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}")
def get_load_balancer(lb_id: str, _: None = Depends(_require_auth)) -> dict:
    reservation = control_plane.get_reservation(lb_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Load balancer reservation not found")
    return {
        "lb_id": reservation.lb_id,
        "name": reservation.config.name,
        "sender_addresses": reservation.config.sender_addresses,
        "ip_family": reservation.config.ip_family,
        "strategy": reservation.config.strategy,
        "created_at": reservation.created_at.isoformat(),
    }


@app.delete("/movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}")
def delete_load_balancer(lb_id: str, _: None = Depends(_require_auth)) -> dict:
    if not control_plane.free_reservation(lb_id):
        raise HTTPException(status_code=404, detail="Load balancer reservation not found")
    return {"status": "freed", "lb_id": lb_id}


@app.get("/movement/streaming/ejfat/control-plane-ip/loadbalancers/{lb_id}/metrics")
def get_load_balancer_metrics(lb_id: str, _: None = Depends(_require_auth)) -> dict:
    metrics = control_plane.get_metrics(lb_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Load balancer reservation not found")
    return metrics
