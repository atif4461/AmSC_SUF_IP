#!/usr/bin/env python3
"""
Receiver + web dashboard for streaming event chunks.

- Receives chunk payloads (pickled dict[str, DataFrame]) via ZeroMQ PULL.
- Updates primary histograms incrementally.
- Maintains ring-buffer snapshots of primary histograms.
- Serves a browser dashboard that displays primary-minus-oldest snapshot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import pickle
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import uvicorn
import zmq
import zmq.asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


DataBundle = Dict[str, pd.DataFrame]


def make_trackfit_view(events: DataBundle) -> pd.DataFrame:
    if "trackFit" not in events or "chargedTrack" not in events:
        return pd.DataFrame()

    charged_cols = [c for c in ["reconstructedPhysicsEvent", "candidateId", "ptype", "jtag"] if c in events["chargedTrack"].columns]
    if not charged_cols:
        return events["trackFit"].copy()

    view = events["trackFit"].join(
        events["chargedTrack"][charged_cols],
        on="chargedTrack",
        how="left",
        rsuffix="_charged",
    ).copy()

    if "Ndof" in view.columns and "chisq" in view.columns:
        ndof = pd.to_numeric(view["Ndof"], errors="coerce")
        chisq = pd.to_numeric(view["chisq"], errors="coerce")
        view["chi2_ndof"] = np.where(ndof > 0, chisq / ndof, np.inf)
    else:
        view["chi2_ndof"] = np.inf

    return view


def z0_best_all_ptypes(events: DataBundle) -> np.ndarray:
    if "z0_best" in events and "z0" in events["z0_best"].columns:
        return pd.to_numeric(events["z0_best"]["z0"], errors="coerce").dropna().to_numpy(dtype=float)

    view = make_trackfit_view(events)
    if view.empty or "z0" not in view.columns:
        return np.array([], dtype=float)

    candidate_keys = [k for k in ["reconstructedPhysicsEvent", "candidateId"] if k in view.columns]
    if not candidate_keys:
        vals = pd.to_numeric(view["z0"], errors="coerce").dropna().to_numpy(dtype=float)
        return vals

    idx = view.groupby(candidate_keys, dropna=False)["chi2_ndof"].idxmin()
    best = view.loc[idx]
    vals = pd.to_numeric(best["z0"], errors="coerce").dropna().to_numpy(dtype=float)
    return vals


def fcal_energy(events: DataBundle) -> np.ndarray:
    if "fcal_energy" in events:
        df = events["fcal_energy"]
        col = "E" if "E" in df.columns else next((c for c in ["energy", "e"] if c in df.columns), None)
        if col is not None:
            return pd.to_numeric(df[col], errors="coerce").dropna().to_numpy(dtype=float)

    if "fcalShower" not in events:
        return np.array([], dtype=float)
    df = events["fcalShower"]
    if df.empty:
        return np.array([], dtype=float)

    col = next((c for c in ["energy", "E", "e"] if c in df.columns), None)
    if col is None:
        energy_like = [c for c in df.columns if "energy" in c.lower()]
        if not energy_like:
            return np.array([], dtype=float)
        col = energy_like[0]
    return pd.to_numeric(df[col], errors="coerce").dropna().to_numpy(dtype=float)


def fcal_xy_points(events: DataBundle) -> np.ndarray:
    if "fcal_xy" in events and {"x", "y"}.issubset(events["fcal_xy"].columns):
        pts = events["fcal_xy"][["x", "y"]].apply(pd.to_numeric, errors="coerce").dropna()
        if not pts.empty:
            return pts[["x", "y"]].to_numpy(dtype=float)

    if "fcalShower" not in events:
        return np.empty((0, 2), dtype=float)
    df = events["fcalShower"]
    if df.empty or not {"x", "y"}.issubset(df.columns):
        return np.empty((0, 2), dtype=float)
    pts = pd.DataFrame(
        {
            "x": pd.to_numeric(df["x"], errors="coerce"),
            "y": pd.to_numeric(df["y"], errors="coerce"),
        }
    ).dropna()
    if pts.empty:
        return np.empty((0, 2), dtype=float)
    return pts[["x", "y"]].to_numpy(dtype=float)


def charged_track_x0y0_points(events: DataBundle) -> np.ndarray:
    """One x0,y0 point per charged track (best fit per chargedTrack when needed)."""
    if "track_x0y0" in events and {"x0", "y0"}.issubset(events["track_x0y0"].columns):
        pts = events["track_x0y0"][["x0", "y0"]].apply(pd.to_numeric, errors="coerce").dropna()
        if not pts.empty:
            return pts.to_numpy(dtype=float)

    if "chargedTrack" in events and {"x0", "y0"}.issubset(events["chargedTrack"].columns):
        cdf = events["chargedTrack"]
        pts = pd.DataFrame(
            {
                "x": pd.to_numeric(cdf["x0"], errors="coerce"),
                "y": pd.to_numeric(cdf["y0"], errors="coerce"),
            }
        ).dropna()
        if not pts.empty:
            return pts[["x", "y"]].to_numpy(dtype=float)

    if "trackFit" not in events:
        return np.empty((0, 2), dtype=float)

    tf = events["trackFit"].copy()
    if not {"x0", "y0"}.issubset(tf.columns):
        return np.empty((0, 2), dtype=float)

    tf["x0"] = pd.to_numeric(tf["x0"], errors="coerce")
    tf["y0"] = pd.to_numeric(tf["y0"], errors="coerce")

    if "chargedTrack" in tf.columns:
        if {"Ndof", "chisq"}.issubset(tf.columns):
            ndof = pd.to_numeric(tf["Ndof"], errors="coerce")
            chisq = pd.to_numeric(tf["chisq"], errors="coerce")
            tf["chi2_ndof"] = np.where(ndof > 0, chisq / ndof, np.inf)
        else:
            tf["chi2_ndof"] = np.inf
        idx = tf.groupby("chargedTrack", dropna=False)["chi2_ndof"].idxmin()
        tf = tf.loc[idx]

    pts = tf[["x0", "y0"]].dropna()
    if pts.empty:
        return np.empty((0, 2), dtype=float)
    return pts.to_numpy(dtype=float)


def pipi_invariant_masses(events: DataBundle) -> np.ndarray:
    """All pi+ pi- invariant masses per event using any available pi hypotheses."""
    if "pipi_mass" in events:
        df = events["pipi_mass"]
        col = "m_pipi" if "m_pipi" in df.columns else next((c for c in ["mass", "m"] if c in df.columns), None)
        if col is not None:
            return pd.to_numeric(df[col], errors="coerce").dropna().to_numpy(dtype=float)

    view = make_trackfit_view(events)
    needed = {"reconstructedPhysicsEvent", "candidateId", "ptype", "px", "py", "pz"}
    if view.empty or not needed.issubset(set(view.columns)):
        return np.array([], dtype=float)

    pi_view = view.loc[view["ptype"].isin(["Pi+", "Pi-"])].copy()
    pi_view["px"] = pd.to_numeric(pi_view["px"], errors="coerce")
    pi_view["py"] = pd.to_numeric(pi_view["py"], errors="coerce")
    pi_view["pz"] = pd.to_numeric(pi_view["pz"], errors="coerce")
    pi_view = pi_view.dropna(subset=["reconstructedPhysicsEvent", "ptype", "px", "py", "pz"])

    m_pi = 0.13957039
    masses: list[float] = []

    for _, ev in pi_view.groupby("reconstructedPhysicsEvent", dropna=False):
        plus = ev.loc[ev["ptype"] == "Pi+", ["px", "py", "pz"]].to_numpy(dtype=float)
        minus = ev.loc[ev["ptype"] == "Pi-", ["px", "py", "pz"]].to_numpy(dtype=float)
        if len(plus) == 0 or len(minus) == 0:
            continue

        for p_plus in plus:
            e_plus = float(np.sqrt(np.dot(p_plus, p_plus) + m_pi * m_pi))
            for p_minus in minus:
                e_minus = float(np.sqrt(np.dot(p_minus, p_minus) + m_pi * m_pi))
                p_tot = p_plus + p_minus
                e_tot = e_plus + e_minus
                m2 = e_tot * e_tot - float(np.dot(p_tot, p_tot))
                masses.append(float(np.sqrt(max(m2, 0.0))))

    if not masses:
        return np.array([], dtype=float)
    return np.asarray(masses, dtype=float)


@dataclass
class HistogramState:
    edges: np.ndarray
    primary: np.ndarray = field(init=False)
    ring: deque[np.ndarray] = field(init=False)
    ring_size: int = 10

    def __post_init__(self) -> None:
        self.primary = np.zeros(len(self.edges) - 1, dtype=np.int64)
        self.ring = deque(maxlen=self.ring_size)

    def reconfigure_ring(self, new_size: int) -> None:
        new_size = max(2, min(30, int(new_size)))
        if new_size == self.ring.maxlen:
            return
        kept = list(self.ring)[-new_size:]
        self.ring = deque(kept, maxlen=new_size)
        self.ring_size = new_size

    def add_values(self, values: np.ndarray) -> None:
        if values.size == 0:
            return
        counts, _ = np.histogram(values, bins=self.edges)
        self.primary += counts.astype(np.int64)

    def snapshot(self) -> None:
        self.ring.append(self.primary.copy())

    def display_counts(self) -> np.ndarray:
        if not self.ring:
            return self.primary.copy()
        oldest = self.ring[0]
        diff = self.primary - oldest
        return np.maximum(diff, 0)


@dataclass
class Histogram2DState:
    x_edges: np.ndarray
    y_edges: np.ndarray
    primary: np.ndarray = field(init=False)
    ring: deque[np.ndarray] = field(init=False)
    ring_size: int = 10

    def __post_init__(self) -> None:
        self.primary = np.zeros((len(self.x_edges) - 1, len(self.y_edges) - 1), dtype=np.int64)
        self.ring = deque(maxlen=self.ring_size)

    def reconfigure_ring(self, new_size: int) -> None:
        new_size = max(2, min(30, int(new_size)))
        if new_size == self.ring.maxlen:
            return
        kept = list(self.ring)[-new_size:]
        self.ring = deque(kept, maxlen=new_size)
        self.ring_size = new_size

    def add_points(self, points: np.ndarray) -> None:
        if points.size == 0:
            return
        counts, _, _ = np.histogram2d(points[:, 0], points[:, 1], bins=[self.x_edges, self.y_edges])
        self.primary += counts.astype(np.int64)

    def snapshot(self) -> None:
        self.ring.append(self.primary.copy())

    def display_counts(self) -> np.ndarray:
        if not self.ring:
            return self.primary.copy()
        oldest = self.ring[0]
        diff = self.primary - oldest
        return np.maximum(diff, 0)


class DashboardState:
    def __init__(self, ring_size: int = 10, update_period: int = 1) -> None:
        self.lock = asyncio.Lock()
        self.update_period = max(1, min(10, int(update_period)))
        self.ring_size = max(2, min(30, int(ring_size)))
        self.events_per_sec: Dict[int, int] = {}
        self.send_bandwidth = None
        self.bandwidth_updated = 0.0
        self.bandwidth_timeout = 10.0

        self.hists: Dict[str, HistogramState] = {
            "z0_best": HistogramState(edges=np.linspace(-250.0, 250.0, 101), ring_size=self.ring_size),
            "fcal_E": HistogramState(edges=np.linspace(0.0, 5.0, 101), ring_size=self.ring_size),
            "m_pipi": HistogramState(edges=np.linspace(0.0, 12.0, 241), ring_size=self.ring_size),
        }
        self.hists2d: Dict[str, Histogram2DState] = {
            "fcal_xy": Histogram2DState(
                x_edges=np.linspace(-120.0, 120.0, 121),
                y_edges=np.linspace(-120.0, 120.0, 121),
                ring_size=self.ring_size,
            ),
            "track_x0y0": Histogram2DState(
                x_edges=np.linspace(-100.0, 100.0, 121),
                y_edges=np.linspace(-100.0, 100.0, 121),
                ring_size=self.ring_size,
            ),
        }

    async def configure(self, ring_size: int | None = None, update_period: int | None = None) -> None:
        async with self.lock:
            if ring_size is not None:
                self.ring_size = max(2, min(30, int(ring_size)))
                for hist in self.hists.values():
                    hist.reconfigure_ring(self.ring_size)
                for hist2d in self.hists2d.values():
                    hist2d.reconfigure_ring(self.ring_size)
            if update_period is not None:
                self.update_period = max(1, min(10, int(update_period)))

    async def ingest_chunk(self, events: DataBundle) -> None:
        z0_vals = z0_best_all_ptypes(events)
        e_vals = fcal_energy(events)
        m_vals = pipi_invariant_masses(events)
        fcal_xy = fcal_xy_points(events)
        track_xy = charged_track_x0y0_points(events)
        reco_events = events.get("reconstructedPhysicsEvent")
        n_events = int(len(reco_events)) if isinstance(reco_events, pd.DataFrame) else 0
        async with self.lock:
            self.hists["z0_best"].add_values(z0_vals)
            self.hists["fcal_E"].add_values(e_vals)
            self.hists["m_pipi"].add_values(m_vals)
            self.hists2d["fcal_xy"].add_points(fcal_xy)
            self.hists2d["track_x0y0"].add_points(track_xy)
            now_sec = int(time.time())
            self.events_per_sec[now_sec] = self.events_per_sec.get(now_sec, 0) + n_events
            cutoff = now_sec - 180
            for sec in [s for s in self.events_per_sec.keys() if s < cutoff]:
                del self.events_per_sec[sec]

    async def ingest_source_bandwidth(self, report: Dict[str, Any]) -> None:
        mb_s = float(report["raw_mb_s"])
        source_count = int(report["source_count"])
        interval = float(report["report_interval"])
        if not math.isfinite(mb_s) or mb_s < 0 or source_count < 1 or not math.isfinite(interval):
            raise ValueError("Invalid source bandwidth report")
        async with self.lock:
            self.send_bandwidth = {
                "mb_s": mb_s, "mbit_s": mb_s * 8, "source_count": source_count,
            }
            self.bandwidth_updated = time.monotonic()
            self.bandwidth_timeout = max(10.0, interval * 3)

    async def take_snapshot(self) -> None:
        async with self.lock:
            for hist in self.hists.values():
                hist.snapshot()
            for hist2d in self.hists2d.values():
                hist2d.snapshot()

    async def payload(self) -> Dict[str, Any]:
        async with self.lock:
            bandwidth = None
            if self.send_bandwidth is not None:
                bandwidth = dict(self.send_bandwidth)
                bandwidth["fresh"] = time.monotonic() - self.bandwidth_updated <= self.bandwidth_timeout
            now_sec = int(time.time())
            # Use only completed whole-second bins.
            # This avoids the rightmost point being artificially low due to
            # including the current partial second.
            end_sec = now_sec - 1
            sec_axis = list(range(end_sec - 60, end_sec + 1))
            eps_x = list(range(0, 61))
            eps_y = [self.events_per_sec.get(s, 0) for s in sec_axis]
            return {
                "ring_size": self.ring_size,
                "update_period": self.update_period,
                "send_bandwidth": bandwidth,
                "events_per_sec": {
                    "x": eps_x,
                    "y": eps_y,
                },
                "heatmaps": {
                    "fcal_xy": {
                        "x_edges": self.hists2d["fcal_xy"].x_edges.tolist(),
                        "y_edges": self.hists2d["fcal_xy"].y_edges.tolist(),
                        "counts": self.hists2d["fcal_xy"].display_counts().T.tolist(),
                    },
                    "track_x0y0": {
                        "x_edges": self.hists2d["track_x0y0"].x_edges.tolist(),
                        "y_edges": self.hists2d["track_x0y0"].y_edges.tolist(),
                        "counts": self.hists2d["track_x0y0"].display_counts().T.tolist(),
                    },
                },
                "plots": {
                    "z0_best": {
                        "edges": self.hists["z0_best"].edges.tolist(),
                        "counts": self.hists["z0_best"].display_counts().tolist(),
                    },
                    "fcal_E": {
                        "edges": self.hists["fcal_E"].edges.tolist(),
                        "counts": self.hists["fcal_E"].display_counts().tolist(),
                    },
                    "m_pipi": {
                        "edges": self.hists["m_pipi"].edges.tolist(),
                        "counts": self.hists["m_pipi"].display_counts().tolist(),
                    },
                },
            }


def build_app(zmq_endpoint: str, ring_size: int, update_period: int) -> FastAPI:
    app = FastAPI(title="Physics Stream Dashboard")
    app.state.dashboard = DashboardState(ring_size=ring_size, update_period=update_period)
    app.state.clients = set()
    app.state.zmq_endpoint = zmq_endpoint
    app.state.tasks = []

    @app.get("/")
    async def index() -> HTMLResponse:
        html = """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Physics Streaming Dashboard</title>
    <script src=\"https://cdn.plot.ly/plotly-cartesian-2.35.2.min.js\"></script>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #111827; color: #f3f4f6; }
    .wrap { max-width: 1200px; margin: 0 auto; padding: 16px; }
        .header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
        .header h1 { margin: 0; font-size: 1.4rem; font-weight: 700; }
        .logo { width: 44px; height: 44px; flex: 0 0 auto; }
    .controls { display: flex; gap: 16px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
    select { padding: 6px 8px; border-radius: 8px; border: 1px solid #374151; background: #1f2937; color: #f3f4f6; }
        .plot { background: #fff; border-radius: 10px; padding: 6px; margin-bottom: 14px; overflow: hidden; min-width: 0; }
        .plot > div { width: 100%; }
        .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: start; }
        .col { display: flex; flex-direction: column; min-width: 0; }
        .mini-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: start; }
        .mini-row .plot { min-width: 0; }
        .top-row { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 12px; margin-bottom: 14px; }
        .top-row > .plot { margin-bottom: 0; }
        .transfer-card { position: relative; height: 272px; box-sizing: border-box; overflow: hidden; border: 1px solid #2d4660; border-radius: 10px; background: radial-gradient(ellipse at 50% 70%, #19364b 0%, #101d31 70%); }
        .transfer-heading { position: relative; z-index: 2; display: flex; justify-content: space-between; align-items: center; padding: 15px 16px 0; }
        .transfer-heading h2 { margin: 0; color: #dce8f3; font-size: 10px; letter-spacing: 1.6px; font-weight: 650; }
        .transfer-status { display: flex; align-items: center; gap: 5px; color: #91a6ba; font-size: 10px; }
        .transfer-status::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: #64748b; }
        .transfer-map { position: absolute; inset: 26px 0 0; width: 100%; height: calc(100% - 48px); }
        .map-state { fill: #1c364d; stroke: #52728a; stroke-width: 0.9; stroke-linejoin: round; }
        .route-guide { fill: none; stroke: #72b8c5; stroke-opacity: .4; stroke-width: 2; }
        .route-glow { fill: none; stroke: #6be3de; stroke-opacity: .09; stroke-width: 14; }
        .route-flow { fill: none; stroke: url(#transferGradient); stroke-width: 3; stroke-linecap: round; stroke-dasharray: 16 30; animation: transfer-flow 1.7s linear infinite; animation-play-state: paused; opacity: 0; }
        .site-halo { fill: #5ce2db; opacity: .1; }
        .site-dot { fill: #8deee5; stroke: #102132; stroke-width: 2; }
        .site-label { fill: #e2f1f9; font-size: 19px; font-weight: 700; letter-spacing: 1px; paint-order: stroke; stroke: #102132; stroke-width: 3px; }
        .bandwidth-readout { position: absolute; z-index: 2; top: 72%; left: 50%; transform: translate(-50%, -25%); width: 68%; text-align: center; border-radius: 12px; background: radial-gradient(ellipse, rgba(12, 27, 43, .98) 20%, rgba(12, 27, 43, .75) 55%, transparent 74%); padding: 7px 0; }
        .bandwidth-number { color: #92eee3; font-size: clamp(28px, 2.8vw, 38px); font-weight: 650; line-height: 1.25; letter-spacing: -1px; font-variant-numeric: tabular-nums; }
        .bandwidth-unit { position: relative; top: 5px; margin-left: 5px; color: #c5e8e8; font-size: 12px; font-weight: 500; letter-spacing: 0; }
        .bandwidth-detail { color: #aac2cf; font-size: 9px; min-height: 14px; }
        .transfer-footer { position: absolute; bottom: 12px; left: 16px; right: 16px; display: flex; justify-content: space-between; color: #7897ab; font-size: 9px; }
        .transfer-card[data-state="live"] .route-flow { animation-play-state: running; opacity: 1; }
        .transfer-card[data-state="live"] .transfer-status { color: #8deee5; }
        .transfer-card[data-state="live"] .transfer-status::before { background: #5ce2db; box-shadow: 0 0 9px #5ce2db88; }
        .transfer-card[data-state="stale"] .bandwidth-number,
        .transfer-card[data-state="waiting"] .bandwidth-number { color: #7897ab; }
        @keyframes transfer-flow { to { stroke-dashoffset: -46; } }
        @media (prefers-reduced-motion: reduce) { .route-flow { animation: none; } }
    .status { opacity: 0.85; font-size: 0.95rem; }
        @media (max-width: 900px) {
            .top-row { grid-template-columns: 1fr; }
            .row { grid-template-columns: 1fr; }
            .mini-row { grid-template-columns: 1fr; }
        }
  </style>
</head>
<body>
  <div class=\"wrap\">
        <div class=\"header\">
            <svg class=\"logo\" viewBox=\"0 0 64 64\" xmlns=\"http://www.w3.org/2000/svg\" aria-label=\"American Science Cloud\">
                <rect x=\"2\" y=\"2\" width=\"60\" height=\"60\" rx=\"12\" fill=\"#0b1220\" stroke=\"#334155\" stroke-width=\"2\"/>
                <path d=\"M17 36c2-6 8-10 14-10 5 0 9 2 12 6 4 0 7 3 7 7s-3 7-7 7H20c-4 0-7-3-7-7 0-3 2-6 4-7z\" fill=\"#93c5fd\"/>
                <circle cx=\"24\" cy=\"25\" r=\"5\" fill=\"#ef4444\"/>
                <circle cx=\"33\" cy=\"21\" r=\"3\" fill=\"#f59e0b\"/>
            </svg>
            <h1>SUF IP D2.1 Demo for the American Science Cloud</h1>
        </div>
    <div class=\"controls\">
      <label>Accumulation time (ring size):
        <select id=\"ringSize\"></select>
      </label>
      <label>Update period (s):
        <select id=\"updatePeriod\"></select>
      </label>
      <div class=\"status\" id=\"status\">Connecting…</div>
    </div>
        <div class='top-row'>
            <div class='plot'><div id='plotEPS'></div></div>
            <section class='transfer-card' id='transferCard' data-state='waiting' aria-label='BNL to NERSC live transfer'>
                <div class='transfer-heading'>
                    <h2>Aggregate Send Bandwith with EJFAT</h2>
                    <span class='transfer-status' id='transferStatus'>Waiting</span>
                </div>
                <!-- TRANSFER_MAP -->
                <div class='bandwidth-readout' role='status' aria-live='polite'>
                    <div class='bandwidth-number'><span id='sendBandwidth'>—</span><span class='bandwidth-unit' id='sendBandwidthUnit'>Gbit/s</span></div>
                    <div class='bandwidth-detail' id='sendBandwidthDetail'>Waiting for source reports</div>
                </div>
                <div class='transfer-footer'><span>BNL, NY &rarr; NERSC, CA</span><span>Offered payload</span></div>
            </section>
        </div>
        <div class=\"row\">
            <div class=\"col\">
                <div class=\"plot\"><div id=\"plotZ0\"></div></div>
                <div class=\"plot\"><div id=\"plotPiPi\"></div></div>
            </div>
            <div class=\"col\">
                <div class=\"plot\"><div id=\"plotFcal\"></div></div>
                <div class=\"mini-row\">
                    <div class=\"plot\"><div id=\"plotFcalXY\"></div></div>
                    <div class=\"plot\"><div id=\"plotTrackXY\"></div></div>
                </div>
            </div>
        </div>
  </div>

<script>
  const ringEl = document.getElementById('ringSize');
  const periodEl = document.getElementById('updatePeriod');
  const statusEl = document.getElementById('status');
  const transferCard = document.getElementById('transferCard');
  function updateTransfer(bandwidth) {
    const fresh = bandwidth && bandwidth.fresh;
    transferCard.dataset.state = fresh ? (bandwidth.mbit_s > 0 ? 'live' : 'idle') : (bandwidth ? 'stale' : 'waiting');
    document.getElementById('transferStatus').textContent = fresh ? (bandwidth.mbit_s > 0 ? 'Live' : 'Idle') : (bandwidth ? 'Stale' : 'Waiting');
    document.getElementById('sendBandwidth').textContent = fresh ? (bandwidth.mbit_s >= 1000 ? bandwidth.mbit_s / 1000 : bandwidth.mbit_s).toFixed(2) : '—';
    document.getElementById('sendBandwidthUnit').textContent = fresh && bandwidth.mbit_s < 1000 ? 'Mbit/s' : 'Gbit/s';
    document.getElementById('sendBandwidthDetail').textContent = fresh ?
      bandwidth.mb_s.toFixed(1) + ' MB/s · ' + bandwidth.source_count + (bandwidth.source_count === 1 ? ' sender' : ' senders') :
      (bandwidth ? 'Source report expired' : 'Waiting for source reports');
  }

  for (let i = 2; i <= 30; i++) {
    const o = document.createElement('option');
    o.value = String(i); o.textContent = String(i); ringEl.appendChild(o);
  }
  for (let i = 1; i <= 10; i++) {
    const o = document.createElement('option');
    o.value = String(i); o.textContent = String(i); periodEl.appendChild(o);
  }

  function centers(edges) {
    const out = [];
    for (let i = 0; i < edges.length - 1; i++) out.push(0.5 * (edges[i] + edges[i + 1]));
    return out;
  }

                function initHistPlot(divId, title, xTitle, color, heightPx) {
        Plotly.newPlot(divId, [{ x: [], y: [], type: 'bar', marker: {color: color || '#2563eb'} }], {
      title,
      xaxis: { title: xTitle },
      yaxis: { title: 'Counts' },
                        height: heightPx || 220,
      margin: { t: 40, r: 12, b: 50, l: 60 },
      uirevision: 'keep'
    }, {displaylogo: false, responsive: true});
  }

    function initSeriesPlot(divId, title) {
        Plotly.newPlot(divId, [{ x: [], y: [], type: 'scatter', mode: 'lines', line: {color: '#059669', width: 2} }], {
            title,
            xaxis: {
                title: 'seconds',
                range: [0, 60],
                tickmode: 'array',
                tickvals: [0, 10, 20, 30, 40, 50, 60],
                ticktext: ['60', '50', '40', '30', '20', '10', '0']
            },
            yaxis: { title: 'Events/s', rangemode: 'tozero' },
            height: 260,
            margin: { t: 40, r: 12, b: 70, l: 60 },
            uirevision: 'keep'
        }, {displaylogo: false, responsive: true});
    }

    initSeriesPlot('plotEPS', 'Events Processed per Second (last 60s)');
    initHistPlot('plotZ0', 'z0 (best chisq/Ndof per candidate)', 'z0', '#dc2626', 220);
    initHistPlot('plotFcal', 'fcalShower energy', 'E', '#2563eb', 220);
    initHistPlot('plotPiPi', 'Invariant mass of all pi+ pi- pairs', 'M(π+π-) [GeV]', '#7c3aed', 320);
    initHeatmapPlot('plotFcalXY', 'fcalShower x,y', 'x', 'y');
    initHeatmapPlot('plotTrackXY', 'charged tracks x0,y0', 'x0', 'y0');

  function updatePlot(divId, edges, counts) {
    const x = centers(edges);
    Plotly.restyle(divId, { x: [x], y: [counts] }, [0]);
  }

    function updateSeries(divId, x, y) {
        Plotly.restyle(divId, { x: [x], y: [y] }, [0]);
    }

    function initHeatmapPlot(divId, title, xTitle, yTitle) {
        Plotly.newPlot(divId, [{
            x: [],
            y: [],
            z: [[]],
            type: 'heatmap',
            colorscale: 'Turbo',
            zmin: 0,
            showscale: true
        }], {
            title,
            xaxis: { title: xTitle },
            yaxis: { title: yTitle },
            height: 320,
            margin: { t: 40, r: 12, b: 50, l: 60 },
            uirevision: 'keep'
        }, {displaylogo: false, responsive: true});
    }

    function updateHeatmap(divId, xEdges, yEdges, counts) {
        Plotly.restyle(divId, {
            x: [centers(xEdges)],
            y: [centers(yEdges)],
            z: [counts]
        }, [0]);
    }

  async function sendConfig() {
    const msg = {
      type: 'config',
      ring_size: Number(ringEl.value),
      update_period: Number(periodEl.value)
    };
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
      window.ws.send(JSON.stringify(msg));
    }
  }

  ringEl.addEventListener('change', sendConfig);
  periodEl.addEventListener('change', sendConfig);

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    window.ws = ws;
    ws.onopen = () => { statusEl.textContent = 'Connected'; };
    ws.onclose = () => {
      updateTransfer({fresh: false});
      statusEl.textContent = 'Disconnected, reconnecting…';
      setTimeout(connect, 1000);
    };
    ws.onerror = () => { statusEl.textContent = 'WebSocket error'; };
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (!data || !data.plots) return;
      updateTransfer(data.send_bandwidth);

      if (data.ring_size) ringEl.value = String(data.ring_size);
      if (data.update_period) periodEl.value = String(data.update_period);

            if (data.events_per_sec) {
                updateSeries('plotEPS', data.events_per_sec.x, data.events_per_sec.y);
            }
      updatePlot('plotZ0', data.plots.z0_best.edges, data.plots.z0_best.counts);
      updatePlot('plotFcal', data.plots.fcal_E.edges, data.plots.fcal_E.counts);
            updatePlot('plotPiPi', data.plots.m_pipi.edges, data.plots.m_pipi.counts);
            if (data.heatmaps) {
                updateHeatmap('plotFcalXY', data.heatmaps.fcal_xy.x_edges, data.heatmaps.fcal_xy.y_edges, data.heatmaps.fcal_xy.counts);
                updateHeatmap('plotTrackXY', data.heatmaps.track_x0y0.x_edges, data.heatmaps.track_x0y0.y_edges, data.heatmaps.track_x0y0.counts);
            }
      statusEl.textContent = `Connected · ring=${data.ring_size} · period=${data.update_period}s`;
    };
  }

    function resizeAllPlots() {
        for (const id of ['plotEPS', 'plotZ0', 'plotFcal', 'plotPiPi', 'plotFcalXY', 'plotTrackXY']) {
            const el = document.getElementById(id);
            if (el) Plotly.Plots.resize(el);
        }
    }

    window.addEventListener('resize', resizeAllPlots);
    setTimeout(resizeAllPlots, 50);
    setTimeout(resizeAllPlots, 250);

  connect();
</script>
</body>
</html>
        """
        html = html.replace("<!-- TRANSFER_MAP -->", Path(__file__).with_name("us-transfer-map.svg").read_text())
        return HTMLResponse(content=html)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        app.state.clients.add(ws)
        try:
            await ws.send_text(json.dumps(await app.state.dashboard.payload()))
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "config":
                    await app.state.dashboard.configure(
                        ring_size=msg.get("ring_size"),
                        update_period=msg.get("update_period"),
                    )
                    await ws.send_text(json.dumps(await app.state.dashboard.payload()))
        except WebSocketDisconnect:
            pass
        finally:
            app.state.clients.discard(ws)

    async def zmq_receiver_loop() -> None:
        ctx = zmq.asyncio.Context.instance()
        socket = ctx.socket(zmq.PULL)
        socket.bind(app.state.zmq_endpoint)
        print(f"ZeroMQ PULL bound at {app.state.zmq_endpoint}")
        try:
            while True:
                payload = await socket.recv()
                try:
                    events = pickle.loads(payload)
                    if isinstance(events, dict):
                        if events.get("_amsc_type") == "source_bandwidth":
                            await app.state.dashboard.ingest_source_bandwidth(events)
                        else:
                            await app.state.dashboard.ingest_chunk(events)
                except Exception as exc:
                    print(f"Dropped invalid payload: {exc}")
        finally:
            socket.close(0)

    async def broadcast_loop() -> None:
        while True:
            period = app.state.dashboard.update_period
            await asyncio.sleep(period)
            await app.state.dashboard.take_snapshot()
            packet = json.dumps(await app.state.dashboard.payload())

            stale = []
            for ws in list(app.state.clients):
                try:
                    await ws.send_text(packet)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                app.state.clients.discard(ws)

    @app.on_event("startup")
    async def startup() -> None:
        app.state.tasks.append(asyncio.create_task(zmq_receiver_loop()))
        app.state.tasks.append(asyncio.create_task(broadcast_loop()))
        print("Receiver startup complete")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        for t in app.state.tasks:
            t.cancel()
        await asyncio.gather(*app.state.tasks, return_exceptions=True)
        app.state.tasks.clear()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run receiver dashboard")
    parser.add_argument("--zmq-endpoint", default="tcp://*:5557", help="Endpoint for ZeroMQ PULL bind")
    parser.add_argument("--host", default="127.0.0.1", help="Web server host")
    parser.add_argument("--port", type=int, default=8000, help="Web server port")
    parser.add_argument("--ring-size", type=int, default=10, help="Initial ring buffer size (2-30)")
    parser.add_argument("--update-period", type=int, default=1, help="Initial update period seconds (1-10)")
    args = parser.parse_args()

    app = build_app(
        zmq_endpoint=args.zmq_endpoint,
        ring_size=args.ring_size,
        update_period=args.update_period,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
