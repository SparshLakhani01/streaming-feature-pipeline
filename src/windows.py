"""Tumbling-window feature computation over the simulated stream.

Windows are fixed, non-overlapping 5-minute buckets assigned by
timestamp. Features per window: event count, purchase count, mean
purchase amount, unique users, purchase share, and mobile share.
All computation is a pure function of the event frame, so the same
input always yields the same windows.
"""

import pandas as pd

WINDOW_SECONDS = 300


def assign_windows(events, window_seconds=WINDOW_SECONDS):
    """Add a window index column (0-based) to a copy of the frame."""
    out = events.copy()
    out["window"] = out["timestamp_sec"] // window_seconds
    return out


def compute_window_features(events, window_seconds=WINDOW_SECONDS):
    """Return one row of features per window."""
    windowed = assign_windows(events, window_seconds)
    rows = []
    for window_id, group in windowed.groupby("window"):
        purchases = group[group["event_type"] == "purchase"]
        rows.append(
            {
                "window": int(window_id),
                "window_start_minute": int(window_id * window_seconds // 60),
                "event_count": int(len(group)),
                "purchase_count": int(len(purchases)),
                "mean_purchase_amount": round(
                    float(purchases["amount"].mean()), 4
                ),
                "unique_users": int(group["user_id"].nunique()),
                "frac_purchase": round(
                    float((group["event_type"] == "purchase").mean()), 4
                ),
                "frac_mobile": round(
                    float((group["channel"] == "mobile").mean()), 4
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("window").reset_index(drop=True)
