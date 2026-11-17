#!/bin/bash
# End-to-end demo: build the venv if needed, run the streaming
# pipeline (simulated stream, windowed features, drift detection),
# run unit tests, smoke-test the API. All metrics printed are
# measured from this run. No external APIs, no message broker.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "== Creating venv and installing dependencies =="
  python3 -m venv --system-site-packages .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo "== 1. Run streaming pipeline =="
.venv/bin/python run_pipeline.py

echo ""
echo "== 2. Unit tests =="
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3

echo ""
echo "== 3. API smoke test =="
.venv/bin/uvicorn api:app --port 8125 --log-level error &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
sleep 4
curl -s http://127.0.0.1:8125/health; echo
curl -s http://127.0.0.1:8125/status | head -c 400; echo
echo ""
echo "Demo complete. Dashboard: results/drift_dashboard.html"
