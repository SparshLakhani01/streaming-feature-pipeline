"""Unit tests for the streaming feature pipeline (stdlib unittest)."""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_pipeline import run_pipeline
from src.drift import (
    confirm_alerts,
    ks_test,
    psi_categorical,
    psi_continuous,
)
from src.stream import generate_events
from src.windows import assign_windows, compute_window_features


class TestStream(unittest.TestCase):
    def test_event_count_and_columns(self):
        events = generate_events(n_minutes=10, seed=1)
        self.assertEqual(len(events), 600)
        for col in ["timestamp_sec", "user_id", "event_type", "channel",
                    "amount"]:
            self.assertIn(col, events.columns)

    def test_deterministic(self):
        a = generate_events(n_minutes=5, seed=3)
        b = generate_events(n_minutes=5, seed=3)
        pd.testing.assert_frame_equal(a, b)

    def test_drift_changes_amounts(self):
        events = generate_events(n_minutes=120, seed=7)
        ref = events[events["minute"] < 60]
        late = events[events["minute"] >= 100]
        ref_mean = ref.loc[ref["event_type"] == "purchase", "amount"].mean()
        late_mean = late.loc[late["event_type"] == "purchase", "amount"].mean()
        self.assertGreater(late_mean, ref_mean * 1.3)


class TestWindows(unittest.TestCase):
    def test_window_assignment(self):
        events = pd.DataFrame({
            "timestamp_sec": [0, 299, 300, 599, 600],
            "user_id": ["u1"] * 5,
            "event_type": ["view"] * 5,
            "channel": ["web"] * 5,
            "amount": [np.nan] * 5,
        })
        out = assign_windows(events, window_seconds=300)
        self.assertEqual(out["window"].tolist(), [0, 0, 1, 1, 2])

    def test_feature_math_on_toy_frame(self):
        events = pd.DataFrame({
            "timestamp_sec": [0, 1, 2, 3],
            "user_id": ["u1", "u1", "u2", "u3"],
            "event_type": ["purchase", "purchase", "view", "view"],
            "channel": ["mobile", "web", "mobile", "web"],
            "amount": [10.0, 30.0, np.nan, np.nan],
        })
        feats = compute_window_features(events, window_seconds=300)
        self.assertEqual(len(feats), 1)
        row = feats.iloc[0]
        self.assertEqual(row["event_count"], 4)
        self.assertEqual(row["purchase_count"], 2)
        self.assertAlmostEqual(row["mean_purchase_amount"], 20.0)
        self.assertEqual(row["unique_users"], 3)
        self.assertAlmostEqual(row["frac_purchase"], 0.5)
        self.assertAlmostEqual(row["frac_mobile"], 0.5)


class TestDrift(unittest.TestCase):
    def test_psi_identical_distributions_near_zero(self):
        rng = np.random.default_rng(0)
        ref = rng.normal(50, 10, size=2000)
        live = rng.normal(50, 10, size=2000)
        self.assertLess(psi_continuous(ref, live), 0.1)

    def test_psi_shifted_distributions_large(self):
        rng = np.random.default_rng(0)
        ref = rng.normal(50, 10, size=2000)
        live = rng.normal(80, 10, size=2000)
        self.assertGreater(psi_continuous(ref, live), 0.25)

    def test_psi_categorical(self):
        self.assertAlmostEqual(
            psi_categorical({"a": 50, "b": 50}, {"a": 50, "b": 50}), 0.0,
            places=6)
        self.assertGreater(
            psi_categorical({"a": 50, "b": 50}, {"a": 90, "b": 10}), 0.25)

    def test_ks_same_distribution_high_p(self):
        rng = np.random.default_rng(1)
        _, p = ks_test(rng.normal(0, 1, 500), rng.normal(0, 1, 500))
        self.assertGreater(p, 0.01)

    def test_ks_shifted_distribution_low_p(self):
        rng = np.random.default_rng(1)
        _, p = ks_test(rng.normal(0, 1, 500), rng.normal(2, 1, 500))
        self.assertLess(p, 0.01)

    def test_confirm_alerts_requires_consecutive(self):
        self.assertEqual(
            confirm_alerts([True, False, True, True, False, True]),
            [False, False, False, True, False, False])


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.html = run_pipeline(seed=7)

    def test_window_count(self):
        self.assertEqual(len(self.report["windows"]), 24)

    def test_drift_detected_after_onset(self):
        det = self.report["detection"]
        self.assertIsNotNone(det["first_confirmed_window"])
        self.assertGreaterEqual(
            det["first_confirmed_window"], det["onset_window"])
        self.assertLessEqual(det["detection_delay_windows"], 3)

    def test_no_false_confirmed_alerts_before_onset(self):
        self.assertEqual(self.report["detection"]
                         ["false_confirmed_before_onset"], 0)

    def test_dashboard_html_mentions_synthetic(self):
        self.assertIn("Synthetic data only", self.html)
        self.assertIn("window", self.html.lower())

    def test_deterministic(self):
        report2, _ = run_pipeline(seed=7)
        self.assertEqual(self.report, report2)


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        import api as api_module

        cls.client = TestClient(api_module.app)

    def test_health(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_status_shape(self):
        body = self.client.get("/status").json()
        self.assertTrue(body["synthetic_data"])
        self.assertIn("latest_window", body)
        self.assertIn("detection", body)

    def test_windows_count(self):
        body = self.client.get("/windows").json()
        self.assertEqual(len(body["windows"]), 24)


if __name__ == "__main__":
    unittest.main()
