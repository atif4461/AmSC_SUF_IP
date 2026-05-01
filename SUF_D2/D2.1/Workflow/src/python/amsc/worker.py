import e2sar_py
import zmq
import os
import signal
import time
import argparse
import numpy as np
import pandas as pd

from amsc import message,credentials,ejfat


def add_arguments(parser):
    parser.add_argument("--name", default="worker0", help="Name for this worker")
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--input-port", type=int, default=12544, help="Port for EJFAT to stream to")
    parser.add_argument("--stats-every", type=int, default=100, help="Print one stats line every N processed messages")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")


def process_data(serialized_data: bytes, verbose: bool) -> bytes:
    msg = message.Message.from_arrow(serialized_data)
    if verbose:
        msg.print_all()
    else:
        msg.print_short()

    def _df(name: str) -> pd.DataFrame:
        if name in msg.keys():
            return msg[name]
        return pd.DataFrame()

    reco = _df("reconstructedPhysicsEvent")
    charged = _df("chargedTrack")
    trackfit = _df("trackFit")
    fcal = _df("fcalShower")

    # Minimal event header needed by monitor for event-rate counting.
    reco_min = pd.DataFrame({"event": np.arange(len(reco), dtype=int)})

    # Build track-fit view used by multiple histogram inputs.
    if not trackfit.empty and not charged.empty and "chargedTrack" in trackfit.columns:
        charged_cols = [c for c in ["reconstructedPhysicsEvent", "candidateId", "ptype", "jtag"] if c in charged.columns]
        if charged_cols:
            tf_view = trackfit.join(
                charged[charged_cols],
                on="chargedTrack",
                how="left",
                rsuffix="_charged",
            ).copy()
        else:
            tf_view = trackfit.copy()
    else:
        tf_view = trackfit.copy()

    if {"Ndof", "chisq"}.issubset(tf_view.columns):
        ndof = pd.to_numeric(tf_view["Ndof"], errors="coerce")
        chisq = pd.to_numeric(tf_view["chisq"], errors="coerce")
        tf_view["chi2_ndof"] = np.where(ndof > 0, chisq / ndof, np.inf)
    else:
        tf_view["chi2_ndof"] = np.inf

    # 1) z0 best hypothesis per candidate
    z0_best_df = pd.DataFrame(columns=["z0"])
    if not tf_view.empty and "z0" in tf_view.columns:
        candidate_keys = [k for k in ["reconstructedPhysicsEvent", "candidateId"] if k in tf_view.columns]
        if candidate_keys:
            best_idx = tf_view.groupby(candidate_keys, dropna=False)["chi2_ndof"].idxmin()
            zvals = pd.to_numeric(tf_view.loc[best_idx, "z0"], errors="coerce").dropna()
        else:
            zvals = pd.to_numeric(tf_view["z0"], errors="coerce").dropna()
        z0_best_df = pd.DataFrame({"z0": zvals.to_numpy(dtype=float)})

    # 2) fcal energy
    fcal_energy_df = pd.DataFrame(columns=["E"])
    if not fcal.empty:
        ecol = next((c for c in ["energy", "E", "e"] if c in fcal.columns), None)
        if ecol is None:
            energy_like = [c for c in fcal.columns if "energy" in c.lower()]
            if energy_like:
                ecol = energy_like[0]
        if ecol is not None:
            evals = pd.to_numeric(fcal[ecol], errors="coerce").dropna()
            fcal_energy_df = pd.DataFrame({"E": evals.to_numpy(dtype=float)})

    # 3) all pi+pi- invariant masses per event (any pi hypotheses)
    pipi_mass_df = pd.DataFrame(columns=["m_pipi"])
    needed = {"reconstructedPhysicsEvent", "ptype", "px", "py", "pz"}
    if not tf_view.empty and needed.issubset(tf_view.columns):
        piv = tf_view.loc[tf_view["ptype"].isin(["Pi+", "Pi-"])].copy()
        piv["px"] = pd.to_numeric(piv["px"], errors="coerce")
        piv["py"] = pd.to_numeric(piv["py"], errors="coerce")
        piv["pz"] = pd.to_numeric(piv["pz"], errors="coerce")
        piv = piv.dropna(subset=["reconstructedPhysicsEvent", "ptype", "px", "py", "pz"])

        m_pi = 0.13957039
        masses = []
        for _, ev in piv.groupby("reconstructedPhysicsEvent", dropna=False):
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
        pipi_mass_df = pd.DataFrame({"m_pipi": np.asarray(masses, dtype=float)})

    # 4) fcal x,y points
    fcal_xy_df = pd.DataFrame(columns=["x", "y"])
    if not fcal.empty and {"x", "y"}.issubset(fcal.columns):
        fxy = pd.DataFrame(
            {
                "x": pd.to_numeric(fcal["x"], errors="coerce"),
                "y": pd.to_numeric(fcal["y"], errors="coerce"),
            }
        ).dropna()
        fcal_xy_df = fxy[["x", "y"]]

    # 5) charged-track x0,y0 points (one per charged track when possible)
    track_x0y0_df = pd.DataFrame(columns=["x0", "y0"])
    if not charged.empty and {"x0", "y0"}.issubset(charged.columns):
        txy = pd.DataFrame(
            {
                "x0": pd.to_numeric(charged["x0"], errors="coerce"),
                "y0": pd.to_numeric(charged["y0"], errors="coerce"),
            }
        ).dropna()
        track_x0y0_df = txy[["x0", "y0"]]
    elif not tf_view.empty and {"x0", "y0"}.issubset(tf_view.columns):
        tf_xy = tf_view.copy()
        tf_xy["x0"] = pd.to_numeric(tf_xy["x0"], errors="coerce")
        tf_xy["y0"] = pd.to_numeric(tf_xy["y0"], errors="coerce")
        if "chargedTrack" in tf_xy.columns:
            idx = tf_xy.groupby("chargedTrack", dropna=False)["chi2_ndof"].idxmin()
            tf_xy = tf_xy.loc[idx]
        tf_xy = tf_xy[["x0", "y0"]].dropna()
        track_x0y0_df = tf_xy

    output_tables = {
        "reconstructedPhysicsEvent": (reco_min, -1, -1),
        "z0_best": (z0_best_df, -1, -1),
        "fcal_energy": (fcal_energy_df, -1, -1),
        "pipi_mass": (pipi_mass_df, -1, -1),
        "fcal_xy": (fcal_xy_df, -1, -1),
        "track_x0y0": (track_x0y0_df, -1, -1),
    }

    output_message = message.Message(output_tables)
    return output_message.to_arrow()


def run(args):

    print("Running worker:")
    print("  name:           ", args.name)
    print("  credential_dir: ", args.credential_dir)
    print("  input_port:     ", args.input_port)
    print("  stats_every:    ", args.stats_every)
    print("  verbose:        ", args.verbose)
    print()

    ejfat_uri_raw = credentials.get_ejfat_uri_raw(args.credential_dir)
    zmq_uri = credentials.get_zmq_address(args.credential_dir)

    print("Obtained credentials:")
    print("  ejfat_uri_raw:  ", ejfat_uri_raw)
    print("  zmq_uri_sink:   ", zmq_uri)
    print()

    # Connect to the zmq socket
    context = zmq.Context.instance()
    push_sock = context.socket(zmq.PUSH)
    push_sock.connect(zmq_uri)

    # Connect to EJFAT
    receiver = ejfat.EjfatReceiver(args.name, ejfat_uri_raw, args.input_port)
    receiver.connect()

    # Loop until killed
    running = True
    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutdown requested...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    processed_count = 0
    dropped_count = 0
    t0 = time.monotonic()
    stats_every = max(1, int(args.stats_every))

    while running:
        if args.verbose:
            print("Worker: Waiting for incoming events...")

        # Receive message
        wait_ms = 3000
        evt_length, evt_bytes, evt_nr, data_id = receiver.recv(wait_ms)

        if evt_length >= 0:
            try:
                if args.verbose:
                    print(f"Received evt {evt_nr} from src {data_id} of length {evt_length}")
                result = process_data(evt_bytes, args.verbose)
                push_sock.send(result)
                processed_count += 1

                if processed_count % stats_every == 0:
                    dt = max(1e-9, time.monotonic() - t0)
                    rate = processed_count / dt
                    print(
                        f"worker[{args.name}] processed={processed_count} "
                        f"dropped={dropped_count} rate={rate:.1f} msg/s"
                    )
            except Exception as exc:
                dropped_count += 1
                print(f"Warning: worker[{args.name}] failed to process event {evt_nr}: {exc}")

    print("Closing ZMQ socket...")
    push_sock.close()
    context.term()

    print("Closing EJFAT connection...")
    receiver.disconnect()


    print("Exited cleanly.")

