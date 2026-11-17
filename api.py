"""FastAPI service exposing drift status for the simulated stream.

The pipeline is deterministic, so state is computed once at startup
from the fixed-seed generator and served from memory. No live data,
no broker, no background jobs.

Endpoints:
  GET /health    liveness
  GET /status    latest window features + drift flags + detection summary
  GET /windows   all windows with per-window drift metrics
"""

import os
import sys

from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_pipeline import run_pipeline

app = FastAPI(title="Streaming Drift Status (synthetic demo)")

_REPORT, _ = run_pipeline(seed=7)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status")
def status():
    latest = _REPORT["windows"][-1]
    return {
        "synthetic_data": True,
        "latest_window": latest,
        "detection": _REPORT["detection"],
        "thresholds": _REPORT["thresholds"],
    }


@app.get("/windows")
def windows():
    return {"synthetic_data": True, "windows": _REPORT["windows"]}
