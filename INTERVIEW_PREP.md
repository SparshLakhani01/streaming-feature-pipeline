# Interview Prep — Streaming Feature Pipeline + Drift Dashboard

## 2-minute explanation

"I built a simulated streaming pipeline that computes windowed
features and detects drift. A fixed-seed generator produces 7,200
synthetic e-commerce events over two hours, with a behavior change
injected at minute 90: purchase amounts go up 1.5x, mobile share
rises, and purchase share rises. The pipeline buckets events into
5-minute tumbling windows, computes features per window, and compares
each live window against the first hour's reference period using PSI
and a Kolmogorov-Smirnov test. A window flags when PSI exceeds 0.25
or the KS test rejects at p less than 0.01, and an alert confirms
only after two consecutive flagged windows. The output is a JSON
report and a static HTML dashboard, plus a FastAPI service exposing
drift status. Measured on this synthetic scenario, detection delay
is one window, five minutes, with zero false confirmed alerts before
onset. One thing I learned while building it: PSI on 90 purchases
per window is noisy enough that the usual 0.1 threshold fired a false
alert, so I moved the alert threshold to the standard 0.25
significant-shift level and documented why."

## Architecture walkthrough

- `src/stream.py`: the generator. One event per second, 500 synthetic
  users, channel and event-type draws with probabilities that shift
  at the onset minute, purchase amounts from a normal distribution
  scaled 1.5x after onset. Deterministic per seed.
- `src/windows.py`: `assign_windows` buckets by integer division of
  the timestamp; `compute_window_features` aggregates per window
  (counts, mean amount, unique users, shares). Pure functions of the
  event frame.
- `src/drift.py`: `psi_continuous` (reference-decile bins, epsilon
  smoothing), `psi_categorical` (category proportions),
  `ks_test` (scipy two-sample KS), and `confirm_alerts` (run-length
  confirmation rule). Thresholds are module constants, stated in one
  place.
- `src/report.py`: builds the dashboard HTML from a string template
  with inline CSS. No JavaScript, no chart library; the table carries
  the information.
- `run_pipeline.py`: orchestration. Builds the reference aggregates,
  scores each window, applies the confirmation rule, computes the
  detection summary (first flag, first confirmation, delay, false
  alarms), and writes the JSON report and HTML dashboard.
- `api.py`: FastAPI app. Runs the pipeline once at startup and serves
  `/health`, `/status`, and `/windows` from memory.
- `tests/test_streaming.py`: 19 tests — window assignment and feature
  math on hand-computed toy frames, PSI/KS behavior on known
  distributions, the confirmation rule, end-to-end detection
  properties (delay within 3 windows, zero false confirms,
  determinism), and API shape via `TestClient`.

## Design tradeoffs

- **Simulated stream, honest labeling.** A real broker would add
  operational complexity without changing the windowing or drift
  math. The README states plainly that there is no Kafka and no live
  ingestion, so the project is judged on what it actually does.
- **PSI plus KS, not one alone.** PSI summarizes binned distribution
  shift and works for categorical mixes; KS is sensitive to any
  distributional change in continuous values and carries a p-value.
  Using both means a shift has two chances to be caught, at the cost
  of more chances for noise to fire, which the confirmation rule
  and the 0.25 threshold control.
- **Two-consecutive confirmation.** Single-window flags are cheap and
  noisy; requiring persistence trades one window of detection delay
  for far fewer false alarms. On this scenario the tradeoff costs
  exactly one window.
- **Static HTML dashboard.** Regenerating a file per run is simpler
  and more auditable than a live dashboard server, and the file can
  be opened anywhere. The FastAPI service covers the programmatic
  access case.
- **Fixed seed, fixed scenario.** Reproducibility first: the same
  command always yields the same report, which makes the metrics
  verifiable. The cost is one scenario instead of a sweep.

## Limitations (say these before being asked)

- No real streaming transport: no broker, no late data, no
  backpressure, no failure modes of a distributed system.
- One drift scenario; gradual drift and variance-only drift are
  untested.
- Tumbling windows only; no sliding or session windows.
- The API serves precomputed state; it ingests nothing live.
- PSI binning from reference deciles can misbehave on discrete or
  heavy-tailed data at small window sizes.

## Future improvements

- More drift scenarios with measured detection delay each.
- Sliding windows, watermarks, and late-event handling.
- Incremental window updates from a live-ingest endpoint.
- Per-feature thresholds and severity levels.
- An optional broker-backed deployment as a labeled extension.

## Likely interview Q&A

**Q: Why PSI and KS together?**
A: They catch different things. PSI is a binned, interpretable
summary that works for categorical distributions like channel mix,
and its 0.1/0.25 bands are a shared industry vocabulary. KS needs no
binning and detects any change in a continuous distribution with a
p-value attached. In this pipeline the amount shift is caught by
both, while the moderate channel and event-type shifts show up in
PSI below the alert threshold, which the dashboard makes visible.

**Q: Why did you raise the PSI threshold from 0.1 to 0.25?**
A: Because I measured the false-alarm behavior. With about 90
purchases per window, PSI in the stable period reached 0.20, and the
0.1 threshold produced a false confirmed alert before onset. The
0.25 level is the standard significant-shift cutoff, it keeps the
stable period quiet, and the real shift clears it by a factor of
five. The dashboard still shows raw PSI, so the moderate shifts are
not hidden by the threshold choice.

**Q: How does the confirmation rule affect detection delay?**
A: It adds exactly one window in the worst case: the first flagged
window cannot confirm by itself. On this scenario onset is window
18, first flag is 18, confirmation is 19, so delay is one window.
Without the rule, delay would be zero windows but false alarms
would be much more likely, which is the wrong trade for an
alerting system.

**Q: What would break with real streaming data?**
A: Late and out-of-order events would land in closed windows;
duplicates would inflate counts; the reference period would go stale
as behavior evolves legitimately; and window sizes would need to
adapt to traffic volume. Those are all reasons the project is
labeled simulated rather than presented as production streaming
infrastructure.

**Q: Why tumbling windows instead of sliding?**
A: Tumbling windows are the simplest correct choice for drift
detection: each event belongs to exactly one window, windows are
independent samples for the statistical tests, and the dashboard
reads cleanly. Sliding windows would correlate adjacent tests and
complicate the confirmation rule without adding detection power for
a step-change scenario.
