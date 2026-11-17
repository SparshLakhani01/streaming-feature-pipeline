"""Simulated event stream generator (synthetic data).

Produces a fixed-seed stream of e-commerce-style events: one event per
second for 120 minutes (7,200 events). The first 60 minutes are the
stable reference period. A behavior change is injected at minute 90
(window 18 of 24): purchase amounts rise 1.5x, the mobile channel
share rises from 0.50 to 0.70, and the purchase event share rises
from 0.30 to 0.45. Everything is invented; there are no real users,
no real orders, and no real money. The stream is simulated in
process: there is no Kafka, no message broker, and no network I/O.
"""

import numpy as np
import pandas as pd

EVENT_TYPES = ["view", "add_to_cart", "purchase"]
CHANNELS = ["mobile", "web"]
DRIFT_ONSET_MINUTE = 90
REFERENCE_MINUTES = 60


def generate_events(n_minutes=120, seed=7, drift_onset_minute=DRIFT_ONSET_MINUTE):
    """Return a DataFrame of synthetic events, one row per second."""
    rng = np.random.default_rng(seed)
    n_events = n_minutes * 60
    minute = np.arange(n_events) // 60
    drifted = minute >= drift_onset_minute

    user_id = rng.integers(0, 500, size=n_events)
    channel_p_mobile = np.where(drifted, 0.70, 0.50)
    channel = np.where(
        rng.uniform(size=n_events) < channel_p_mobile, "mobile", "web"
    )
    purchase_p = np.where(drifted, 0.45, 0.30)
    event_type = []
    for p_purchase in purchase_p:
        r = rng.uniform()
        if r < p_purchase:
            event_type.append("purchase")
        elif r < p_purchase + 0.15:
            event_type.append("add_to_cart")
        else:
            event_type.append("view")
    event_type = np.array(event_type)

    amount = np.where(
        event_type == "purchase",
        np.clip(rng.normal(50, 15, size=n_events), 5, 200),
        np.nan,
    )
    amount = np.where(drifted & (event_type == "purchase"), amount * 1.5, amount)
    amount = np.round(amount, 2)

    return pd.DataFrame(
        {
            "timestamp_sec": np.arange(n_events),
            "minute": minute,
            "user_id": [f"SYN-USER-{u:04d}" for u in user_id],
            "event_type": event_type,
            "channel": channel,
            "amount": amount,
            "drifted": drifted,
        }
    )
