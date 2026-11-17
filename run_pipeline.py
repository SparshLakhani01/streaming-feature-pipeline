#!/usr/bin/env python3
"""Run the streaming pipeline: simulate, window, detect drift, report.

Reference period: first 60 minutes (windows 0-11). Live period:
windows 12-23, with an injected behavior change at minute 90
(window 18). For each live window, PSI and KS statistics are
computed against the reference period, and alerts follow the
2-consecutive-windows confirmation rule. Writes a JSON report and a
static HTML dashboard. Fully deterministic for a fixed seed.

Usage:
    python run_pipeline.py [--seed 7] [--output-dir results]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.drift import (
    CONFIRM_CONSECUTIVE,
    KS_P_FLAG_THRESHOLD,
    PSI_FLAG_THRESHOLD,
    confirm_alerts,
    ks_test,
    psi_categorical,
    psi_continuous,
)
from src.report import build_dashboard
from src.stream import DRIFT_ONSET_MINUTE, REFERENCE_MINUTES, generate_events
from src.windows import WINDOW_SECONDS, assign_windows, compute_window_features

BASE = os.path.dirname(os.path.abspath(__file__))


def run_pipeline(seed=7):
    """Execute the pipeline; return (report dict, dashboard HTML)."""
    events = generate_events(seed=seed)
    windowed = assign_windows(events)
    features = compute_window_features(events)
    ref_last = REFERENCE_MINUTES * 60 // WINDOW_SECONDS - 1
    onset_window = DRIFT_ONSET_MINUTE * 60 // WINDOW_SECONDS

    ref = windowed[windowed["window"] <= ref_last]
    ref_amounts = ref.loc[ref["event_type"] == "purchase", "amount"]
    ref_channel = ref["channel"].value_counts().to_dict()
    ref_event_type = ref["event_type"].value_counts().to_dict()

    windows = []
    for _, row in features.iterrows():
        w = int(row["window"])
        group = windowed[windowed["window"] == w]
        live_amounts = group.loc[group["event_type"] == "purchase", "amount"]
        amount_psi = psi_continuous(ref_amounts, live_amounts)
        ks_stat, ks_p = ks_test(ref_amounts, live_amounts)
        channel_psi = psi_categorical(
            ref_channel, group["channel"].value_counts().to_dict()
        )
        event_type_psi = psi_categorical(
            ref_event_type, group["event_type"].value_counts().to_dict()
        )
        is_live = w > ref_last
        flagged = is_live and (
            amount_psi > PSI_FLAG_THRESHOLD
            or ks_p < KS_P_FLAG_THRESHOLD
            or channel_psi > PSI_FLAG_THRESHOLD
            or event_type_psi > PSI_FLAG_THRESHOLD
        )
        windows.append(
            {
                "window": w,
                "window_start_minute": int(row["window_start_minute"]),
                "event_count": int(row["event_count"]),
                "purchase_count": int(row["purchase_count"]),
                "mean_purchase_amount": float(row["mean_purchase_amount"]),
                "unique_users": int(row["unique_users"]),
                "frac_purchase": float(row["frac_purchase"]),
                "frac_mobile": float(row["frac_mobile"]),
                "amount_psi": round(amount_psi, 4),
                "amount_ks_stat": round(ks_stat, 4),
                "amount_ks_p": round(ks_p, 6),
                "channel_psi": round(channel_psi, 4),
                "event_type_psi": round(event_type_psi, 4),
                "is_live": bool(is_live),
                "flagged": bool(flagged),
            }
        )

    confirmed = confirm_alerts(
        [w["flagged"] for w in windows], consecutive=CONFIRM_CONSECUTIVE
    )
    for w, conf in zip(windows, confirmed):
        w["confirmed"] = bool(conf and w["is_live"])

    live_windows = [w for w in windows if w["is_live"]]
    flagged_live = [w["window"] for w in live_windows if w["flagged"]]
    confirmed_live = [w["window"] for w in live_windows if w["confirmed"]]
    first_confirmed = confirmed_live[0] if confirmed_live else None
    detection = {
        "onset_window": onset_window,
        "first_flagged_window": flagged_live[0] if flagged_live else None,
        "first_confirmed_window": first_confirmed,
        "detection_delay_windows": (
            first_confirmed - onset_window if first_confirmed is not None
            else None
        ),
        "false_confirmed_before_onset": sum(
            1 for w in live_windows
            if w["confirmed"] and w["window"] < onset_window
        ),
        "live_windows_flagged": len(flagged_live),
        "live_windows_total": len(live_windows),
    }

    report = {
        "synthetic_data": True,
        "seed": seed,
        "n_events": len(events),
        "window_seconds": WINDOW_SECONDS,
        "reference_windows": [0, ref_last],
        "thresholds": {
            "psi_flag": PSI_FLAG_THRESHOLD,
            "ks_p_flag": KS_P_FLAG_THRESHOLD,
            "confirm_consecutive": CONFIRM_CONSECUTIVE,
        },
        "detection": detection,
        "windows": windows,
    }
    summary_text = (
        f"{len(events)} synthetic events over 120 minutes, "
        f"{len(windows)} 5-minute windows, seed {seed}."
    )
    html = build_dashboard(
        windows, detection, summary_text, onset_window,
        DRIFT_ONSET_MINUTE, ref_last,
        {"psi_flag": PSI_FLAG_THRESHOLD,
         "ks_p_flag": KS_P_FLAG_THRESHOLD,
         "confirm_consecutive": CONFIRM_CONSECUTIVE},
    )
    return report, html


def main():
    parser = argparse.ArgumentParser(description="Streaming drift pipeline")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    report, html = run_pipeline(seed=args.seed)
    out_dir = os.path.join(BASE, args.output_dir)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "drift_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(out_dir, "drift_dashboard.html"), "w",
              encoding="utf-8") as fh:
        fh.write(html)

    det = report["detection"]
    print(f"Events: {report['n_events']} synthetic | "
          f"windows: {len(report['windows'])} x 5 min | seed {args.seed}")
    print(f"Drift onset: window {det['onset_window']} "
          f"(minute {DRIFT_ONSET_MINUTE})")
    print(f"First flagged window: {det['first_flagged_window']}")
    print(f"First confirmed alert: {det['first_confirmed_window']}")
    print(f"Detection delay: {det['detection_delay_windows']} window(s)")
    print(f"False confirmed alerts before onset: "
          f"{det['false_confirmed_before_onset']}")
    print(f"Live windows flagged: {det['live_windows_flagged']}/"
          f"{det['live_windows_total']}")
    print(f"Report: {args.output_dir}/drift_report.json, dashboard: "
          f"{args.output_dir}/drift_dashboard.html")


if __name__ == "__main__":
    main()
