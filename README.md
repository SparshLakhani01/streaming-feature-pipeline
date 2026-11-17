# Streaming Feature Pipeline + Drift Dashboard

A simulated streaming pipeline: a fixed-seed event generator, tumbling
5-minute windows with per-window feature computation, drift detection
(PSI + Kolmogorov-Smirnov) against a reference period, a static HTML
drift dashboard regenerated on every run, and a FastAPI service that
exposes drift status. Everything runs in-process with no message
broker, no external services, and no network calls.

## Data disclosure — read this first

**All data in this project is synthetic.** The event stream is
invented by `src/stream.py`: 7,200 e-commerce-style events (one per
second for 120 minutes, seed 7) with made-up user IDs (`SYN-USER-*`),
event types, channels, and purchase amounts. There are no real users,
no real orders, and no real money. The behavior change at minute 90
is injected deliberately so drift detection has something real (in
the synthetic sense) to find. Every report and API response is
labeled synthetic.

## What it does

1. **Simulate** (`src/stream.py`): 120 minutes of events. The first
   60 minutes are stable. At minute 90 the generator shifts purchase
   amounts up 1.5x, the mobile channel share from 0.50 to 0.70, and
   the purchase event share from 0.30 to 0.45.
2. **Window** (`src/windows.py`): tumbling 5-minute windows (24
   total). Per-window features: event count, purchase count, mean
   purchase amount, unique users, purchase share, mobile share.
3. **Detect** (`src/drift.py`): for each live window (12-23), PSI and
   KS statistics are computed against the reference period (windows
   0-11): amount PSI + KS test on purchase amounts, PSI on channel
   mix, PSI on event-type mix. A window is flagged when PSI > 0.25
   (the standard significant-shift level) or KS p < 0.01. An alert
   is confirmed only after 2 consecutive flagged windows.
4. **Report** (`src/report.py`, `run_pipeline.py`): a JSON report
   (`results/drift_report.json`) and a static HTML dashboard
   (`results/drift_dashboard.html`) with the per-window table and
   detection summary.
5. **Serve** (`api.py`): FastAPI with `GET /health`, `GET /status`
   (latest window + detection summary), and `GET /windows` (all
   windows). State is computed once at startup from the fixed-seed
   generator and served from memory.

### Why the PSI threshold is 0.25, not 0.1

PSI on ~90 purchases per window is noisy: in the stable reference
period, window PSI values reach 0.20 with no real change, and a 0.1
alert threshold produced a false confirmed alert before onset in an
earlier run of this pipeline. The 0.25 threshold is the standard
significant-shift level and keeps the stable period quiet while the
injected shift (amount PSI 1.17-1.70 after onset) still clears it by
a wide margin. Raw PSI values are shown in the dashboard so moderate
shifts stay visible even when they do not alert.

## Measured results

Measured by running `./demo.sh` (7,200 synthetic events, 24 windows,
seed 7). Two consecutive runs produced byte-identical reports.

| measure | value | context |
|---|---|---|
| Drift onset | window 18 (minute 90) | injected by the generator |
| First flagged window | 18 | same window as onset |
| First confirmed alert | 19 | 2-consecutive-windows rule |
| Detection delay | 1 window (5 minutes) | confirmed alert minus onset |
| False confirmed alerts before onset | 0 | 6 pre-onset live windows |
| Live windows flagged | 6/12 | all 6 post-onset windows |
| Post-onset amount PSI range | 1.17-1.70 | 6 post-onset windows |
| Post-onset KS p (amount) | 0.0 (all 6 windows) | vs reference amounts |
| Stable-period max amount PSI | 0.204 | 18 pre-onset windows |

Channel PSI (0.105-0.187) and event-type PSI (0.106-0.193) after onset
stay below the 0.25 alert threshold: those shifts are real but
moderate, and detection is driven by the amount metrics. The
dashboard shows all three so the distinction is visible rather than
hidden.

## How to run

```bash
./demo.sh            # creates .venv, runs pipeline, tests, API smoke test
```

Or manually:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run_pipeline.py [--seed 7]
.venv/bin/python -m unittest discover -s tests
.venv/bin/uvicorn api:app --port 8000
open results/drift_dashboard.html
```

## Project layout

```
src/stream.py         fixed-seed synthetic event generator (drift at min 90)
src/windows.py        tumbling windows + per-window feature computation
src/drift.py          PSI (continuous + categorical), KS test, confirmation rule
src/report.py         static HTML dashboard builder
run_pipeline.py       CLI: simulate, window, detect, write JSON + HTML
api.py                FastAPI drift-status service
tests/test_streaming.py  19 unit tests (stdlib unittest + TestClient)
results/              drift_report.json + drift_dashboard.html (verified run)
```

## Limitations (honest)

- The stream is simulated, not real streaming: no Kafka, no
  backpressure, no late/out-of-order events, no exactly-once
  semantics. The windowing and drift math is real; the transport is
  a loop over a generated frame.
- One fixed seed, one drift scenario. Detection delay and false
  alarms are measured for this scenario only; other drift shapes
  (gradual drift, variance-only drift, new categories) would behave
  differently and are not tested here.
- Windows are tumbling and aligned to the stream start; sliding
  windows and session windows are not implemented.
- The API serves precomputed state from startup; it does not ingest
  live events.
- PSI binning uses reference deciles, which can be unstable for
  heavy-tailed or discrete distributions at small window sizes.

## Future improvements

- Gradual-drift and variance-shift scenarios, with detection delay
  measured for each.
- Sliding windows and late-event handling with watermarks.
- A live-ingest endpoint that appends events and recomputes the
  current window incrementally.
- Per-feature alerting with separate thresholds and a severity scale,
  instead of one combined flag.
- A real broker-backed variant (e.g. Kafka + a consumer) as a
  separate, explicitly labeled extension.
