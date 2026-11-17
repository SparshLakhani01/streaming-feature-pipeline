"""Drift dashboard HTML report builder (static, dependency-free)."""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Streaming Drift Dashboard (Synthetic Data)</title>
<style>
body {{ font-family: sans-serif; margin: 2em; color: #222; }}
h1 {{ font-size: 1.4em; }}
table {{ border-collapse: collapse; margin: 1em 0; }}
th, td {{ border: 1px solid #999; padding: 4px 10px; text-align: right; }}
th {{ background: #eee; }}
.flag {{ background: #ffd9d9; }}
.ok {{ background: #dff0d8; }}
.note {{ color: #555; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>Streaming Drift Dashboard</h1>
<p class="note"><strong>Synthetic data only.</strong> Simulated event stream:
{summary}</p>
<h2>Windows</h2>
<table>
<tr><th>Window</th><th>Start (min)</th><th>Events</th><th>Mean amount</th>
<th>Frac purchase</th><th>Frac mobile</th><th>Amount PSI</th><th>KS p</th>
<th>Channel PSI</th><th>Event-type PSI</th><th>Flagged</th><th>Confirmed</th></tr>
{rows}
</table>
<h2>Detection summary</h2>
<ul>
<li>Drift injected at window {onset} (minute {onset_minute}).</li>
<li>First flagged live window: {first_flagged}.</li>
<li>First confirmed alert: {first_confirmed}.</li>
<li>Detection delay: {delay} window(s) after onset.</li>
<li>Confirmed alerts before onset (false alarms): {false_alarms}.</li>
</ul>
<p class="note">Thresholds: PSI &gt; {psi_threshold} or KS p &lt; {ks_threshold}
flags a window; {confirm} consecutive flagged windows confirm an alert.
Reference period: windows 0-{ref_last} (first 60 minutes).</p>
</body>
</html>
"""


def build_dashboard(windows, detection, summary_text, onset, onset_minute,
                    ref_last, thresholds):
    """windows: list of dicts with per-window metrics and flags."""
    rows = []
    for w in windows:
        cls = "flag" if w["confirmed"] else ("flag" if w["flagged"] else "ok")
        rows.append(
            "<tr class=\"{cls}\"><td>{window}</td><td>{start}</td>"
            "<td>{events}</td><td>{amount}</td><td>{frac_p}</td>"
            "<td>{frac_m}</td><td>{psi}</td><td>{ks_p}</td>"
            "<td>{ch_psi}</td><td>{et_psi}</td>"
            "<td>{flagged}</td><td>{confirmed}</td></tr>".format(
                cls=cls, window=w["window"], start=w["window_start_minute"],
                events=w["event_count"], amount=w["mean_purchase_amount"],
                frac_p=w["frac_purchase"], frac_m=w["frac_mobile"],
                psi=w["amount_psi"], ks_p=w["amount_ks_p"],
                ch_psi=w["channel_psi"], et_psi=w["event_type_psi"],
                flagged="yes" if w["flagged"] else "no",
                confirmed="yes" if w["confirmed"] else "no",
            )
        )
    return HTML_TEMPLATE.format(
        summary=summary_text, rows="\n".join(rows), onset=onset,
        onset_minute=onset_minute,
        first_flagged=detection["first_flagged_window"],
        first_confirmed=detection["first_confirmed_window"],
        delay=detection["detection_delay_windows"],
        false_alarms=detection["false_confirmed_before_onset"],
        ref_last=ref_last,
        psi_threshold=thresholds["psi_flag"],
        ks_threshold=thresholds["ks_p_flag"],
        confirm=thresholds["confirm_consecutive"],
    )
