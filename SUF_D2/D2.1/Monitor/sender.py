#!/usr/bin/env python3
"""
Synthetic streaming sender for physics-event chunks.

Reads a seed pickle file (dict[str, pandas.DataFrame]), samples events,
smears float columns using dataset RMS values, and sends chunks over ZeroMQ.
"""

from __future__ import annotations

import argparse
import pickle
import time
from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd
import zmq


DataBundle = Dict[str, pd.DataFrame]


@dataclass
class FloatStats:
    mean: float
    rms: float


def load_events(path: str) -> DataBundle:
    with open(path, "rb") as f:
        data = pickle.load(f)
    if not isinstance(data, dict):
        raise TypeError("Expected top-level dict in pickle payload")
    for k, v in data.items():
        if not isinstance(v, pd.DataFrame):
            raise TypeError(f"Expected DataFrame for key '{k}', got {type(v)}")
    return data


def compute_float_stats(events: DataBundle) -> Dict[str, Dict[str, FloatStats]]:
    stats: Dict[str, Dict[str, FloatStats]] = {}
    for table_name, df in events.items():
        table_stats: Dict[str, FloatStats] = {}
        for col in df.columns:
            if pd.api.types.is_float_dtype(df[col]):
                values = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
                mean = float(np.nanmean(values)) if values.size else 0.0
                rms = float(np.nanstd(values)) if values.size else 0.0
                if not np.isfinite(rms):
                    rms = 0.0
                if not np.isfinite(mean):
                    mean = 0.0
                table_stats[col] = FloatStats(mean=mean, rms=rms)
        stats[table_name] = table_stats
    return stats


def smear_float_columns(
    table_name: str,
    df: pd.DataFrame,
    stats: Dict[str, Dict[str, FloatStats]],
    rng: np.random.Generator,
) -> pd.DataFrame:
    out = df.copy()
    table_stats = stats.get(table_name, {})
    for col, st in table_stats.items():
        if col in out.columns and len(out):
            sigma = max(0.0, float(st.rms))
            if sigma > 0.0:
                out[col] = pd.to_numeric(out[col], errors="coerce") + rng.normal(
                    loc=0.0, scale=sigma, size=len(out)
                )
    return out


def build_smeared_chunk(
    source: DataBundle,
    sampled_event_ids: np.ndarray,
    stats: Dict[str, Dict[str, FloatStats]],
    rng: np.random.Generator,
) -> DataBundle:
    out_parts: Dict[str, list[pd.DataFrame]] = {k: [] for k in source}
    next_idx: Dict[str, int] = {k: 0 for k in source}

    if "reconstructedPhysicsEvent" not in source:
        raise KeyError("Source payload is missing 'reconstructedPhysicsEvent'")

    reco_df = source["reconstructedPhysicsEvent"]
    charged_df = source.get("chargedTrack")
    trackfit_df = source.get("trackFit")

    for old_evt in sampled_event_ids:
        evt_rows = reco_df.loc[[old_evt]].copy() if old_evt in reco_df.index else reco_df.iloc[0:0].copy()
        evt_rows = smear_float_columns("reconstructedPhysicsEvent", evt_rows, stats, rng)
        evt_new_indices = np.arange(next_idx["reconstructedPhysicsEvent"], next_idx["reconstructedPhysicsEvent"] + len(evt_rows))
        evt_rows.index = evt_new_indices
        next_idx["reconstructedPhysicsEvent"] += len(evt_rows)
        out_parts["reconstructedPhysicsEvent"].append(evt_rows)

        if len(evt_rows) == 0:
            continue
        new_evt_id = int(evt_new_indices[0])

        # Tables with direct reconstructedPhysicsEvent foreign key
        for table_name, df in source.items():
            if table_name in {"reconstructedPhysicsEvent", "chargedTrack", "trackFit"}:
                continue
            if "reconstructedPhysicsEvent" not in df.columns:
                continue

            sub = df.loc[df["reconstructedPhysicsEvent"] == old_evt].copy()
            if sub.empty:
                continue
            sub["reconstructedPhysicsEvent"] = new_evt_id
            sub = smear_float_columns(table_name, sub, stats, rng)

            new_indices = np.arange(next_idx[table_name], next_idx[table_name] + len(sub))
            sub.index = new_indices
            next_idx[table_name] += len(sub)
            out_parts[table_name].append(sub)

        # chargedTrack + trackFit remap chain
        charged_map: Dict[int, int] = {}
        if charged_df is not None and "reconstructedPhysicsEvent" in charged_df.columns:
            csub = charged_df.loc[charged_df["reconstructedPhysicsEvent"] == old_evt].copy()
            if not csub.empty:
                csub["reconstructedPhysicsEvent"] = new_evt_id
                csub_old_idx = csub.index.to_numpy()
                csub = smear_float_columns("chargedTrack", csub, stats, rng)

                c_new_indices = np.arange(next_idx["chargedTrack"], next_idx["chargedTrack"] + len(csub))
                csub.index = c_new_indices
                next_idx["chargedTrack"] += len(csub)
                out_parts["chargedTrack"].append(csub)
                charged_map = {int(old): int(new) for old, new in zip(csub_old_idx, c_new_indices)}

        if trackfit_df is not None and "chargedTrack" in trackfit_df.columns and charged_map:
            old_charged = list(charged_map.keys())
            tsub = trackfit_df.loc[trackfit_df["chargedTrack"].isin(old_charged)].copy()
            if not tsub.empty:
                tsub["chargedTrack"] = tsub["chargedTrack"].map(charged_map)
                tsub = tsub.dropna(subset=["chargedTrack"])
                tsub["chargedTrack"] = tsub["chargedTrack"].astype(int)
                tsub = smear_float_columns("trackFit", tsub, stats, rng)

                t_new_indices = np.arange(next_idx["trackFit"], next_idx["trackFit"] + len(tsub))
                tsub.index = t_new_indices
                next_idx["trackFit"] += len(tsub)
                out_parts["trackFit"].append(tsub)

    out: DataBundle = {}
    for table_name, source_df in source.items():
        parts = out_parts.get(table_name, [])
        if parts:
            out_df = pd.concat(parts, axis=0)
            out_df = out_df.reset_index(drop=True)
        else:
            out_df = source_df.iloc[0:0].copy()
            out_df = out_df.reset_index(drop=True)
        out[table_name] = out_df
    return out


def choose_chunk_size(rng: np.random.Generator, mean: float = 10.0, sigma: float = 2.0) -> int:
    n = int(round(rng.normal(loc=mean, scale=sigma)))
    return max(1, min(50, n))


def main() -> None:
    parser = argparse.ArgumentParser(description="Send synthetic event chunks over ZeroMQ")
    parser.add_argument("--input", default="data/first_10_events.pickle", help="Path to seed pickle file")
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5557", help="ZeroMQ endpoint for PUSH socket")
    parser.add_argument(
        "--chunks-per-second",
        type=float,
        default=6.0,
        help="Target chunk send rate in chunks/second",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Seconds between chunks (legacy override; if set, chunks-per-second = 1/interval)",
    )
    parser.add_argument("--seed", type=int, default=12345, help="RNG seed")
    args = parser.parse_args()

    if args.interval is not None:
        if args.interval <= 0:
            raise ValueError("--interval must be > 0")
        chunks_per_second = 1.0 / args.interval
    else:
        chunks_per_second = float(args.chunks_per_second)

    if chunks_per_second <= 0:
        raise ValueError("--chunks-per-second must be > 0")
    send_period = 1.0 / chunks_per_second

    rng = np.random.default_rng(args.seed)
    source = load_events(args.input)
    stats = compute_float_stats(source)

    reco_df = source["reconstructedPhysicsEvent"]
    event_ids = reco_df.index.to_numpy()
    if event_ids.size == 0:
        raise RuntimeError("No events available in reconstructedPhysicsEvent")

    print(f"Loaded source with {len(event_ids)} seed events")
    print(f"Connecting PUSH socket to {args.endpoint}")
    print(f"Target send rate: {chunks_per_second:.3f} chunks/s ({send_period:.4f} s/chunk)")

    ctx = zmq.Context.instance()
    socket = ctx.socket(zmq.PUSH)
    socket.connect(args.endpoint)

    try:
        next_send_t = time.monotonic()
        log_window_start = time.monotonic()
        chunks_in_window = 0
        events_in_window = 0

        while True:
            n_events = choose_chunk_size(rng)
            sampled = rng.choice(event_ids, size=n_events, replace=True)
            chunk = build_smeared_chunk(source, sampled, stats, rng)

            payload = pickle.dumps(chunk, protocol=pickle.HIGHEST_PROTOCOL)
            socket.send(payload)

            sent_events = len(chunk.get("reconstructedPhysicsEvent", []))
            chunks_in_window += 1
            events_in_window += int(sent_events)

            now = time.monotonic()
            while now - log_window_start >= 1.0:
                chunk_period = (1.0 / chunks_in_window) if chunks_in_window > 0 else float("inf")
                event_rate = float(events_in_window)
                print(
                    "last 1s: "
                    f"chunks={chunks_in_window:3d} "
                    f"chunk_period={chunk_period:7.4f} s/chunk "
                    f"event_rate={event_rate:7.2f} events/s"
                )
                chunks_in_window = 0
                events_in_window = 0
                log_window_start += 1.0

            next_send_t += send_period
            sleep_dt = next_send_t - time.monotonic()
            if sleep_dt > 0:
                time.sleep(sleep_dt)
            else:
                next_send_t = time.monotonic()
    except KeyboardInterrupt:
        print("\nSender stopped.")
    finally:
        socket.close(0)


if __name__ == "__main__":
    main()
