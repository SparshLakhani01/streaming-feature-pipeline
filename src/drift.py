"""Drift detection: Population Stability Index (PSI) and KS test.

PSI compares binned distributions: for continuous values, bins are
the deciles of the reference distribution; for categorical values,
bins are the categories. The standard interpretation is PSI < 0.1
stable, 0.1-0.25 moderate shift, > 0.25 significant shift. This
project flags a window when PSI > 0.25 (the significant-shift level)
or, for continuous values, when the two-sample KS test rejects at
p < 0.01. The 0.25 level is used instead of 0.1 because PSI computed
on ~90 purchases per window is noisy: in the stable reference
period, window PSI values reach 0.20 without any real change, so a
0.1 alert threshold would fire on noise. The dashboard still shows
raw PSI values so moderate shifts stay visible. A feature-level
alert is *confirmed* only after 2 consecutive flagged windows,
which suppresses single-window noise.

All thresholds are stated here and in the README; nothing is tuned
silently after seeing results.
"""

import numpy as np
from scipy import stats

PSI_FLAG_THRESHOLD = 0.25
KS_P_FLAG_THRESHOLD = 0.01
CONFIRM_CONSECUTIVE = 2
_EPS = 1e-4


def psi_continuous(reference, live, n_bins=10):
    """PSI between two numeric samples; bins from reference deciles."""
    reference = np.asarray(reference, dtype=float)
    live = np.asarray(live, dtype=float)
    reference = reference[~np.isnan(reference)]
    live = live[~np.isnan(live)]
    if len(reference) == 0 or len(live) == 0:
        return 0.0
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0] -= 1e-9
    edges[-1] += 1e-9
    ref_counts, _ = np.histogram(reference, bins=edges)
    live_counts, _ = np.histogram(live, bins=edges)
    ref_prop = ref_counts / ref_counts.sum()
    live_prop = live_counts / live_counts.sum()
    ref_prop = np.where(ref_prop == 0, _EPS, ref_prop)
    live_prop = np.where(live_prop == 0, _EPS, live_prop)
    return float(np.sum((live_prop - ref_prop) * np.log(live_prop / ref_prop)))


def psi_categorical(reference_counts, live_counts):
    """PSI between two category-count dicts over their union of keys."""
    keys = set(reference_counts) | set(live_counts)
    ref_total = sum(reference_counts.values())
    live_total = sum(live_counts.values())
    psi = 0.0
    for key in keys:
        ref_p = max(reference_counts.get(key, 0) / ref_total, _EPS)
        live_p = max(live_counts.get(key, 0) / live_total, _EPS)
        psi += (live_p - ref_p) * np.log(live_p / ref_p)
    return float(psi)


def ks_test(reference, live):
    """Two-sample KS test; returns (statistic, pvalue)."""
    reference = np.asarray(reference, dtype=float)
    live = np.asarray(live, dtype=float)
    reference = reference[~np.isnan(reference)]
    live = live[~np.isnan(live)]
    if len(reference) == 0 or len(live) == 0:
        return 0.0, 1.0
    result = stats.ks_2samp(reference, live)
    return float(result.statistic), float(result.pvalue)


def confirm_alerts(flags, consecutive=CONFIRM_CONSECUTIVE):
    """Return per-position confirmed flags (True from the Nth consecutive)."""
    confirmed = []
    run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        confirmed.append(run >= consecutive)
    return confirmed
