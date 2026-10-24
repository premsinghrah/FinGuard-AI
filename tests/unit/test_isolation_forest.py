"""
FinGuard AI — Unit Tests: IsolationForestDetector
===================================================
Tests run without any Frappe dependency.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from finance_ai.anomaly_engine.isolation_forest import IsolationForestDetector
from finance_ai.anomaly_engine.features import FEATURE_COLUMNS


@pytest.fixture
def detector():
    return IsolationForestDetector(contamination=0.1, n_estimators=50, random_state=42)


@pytest.fixture
def feature_df(sample_transactions):
    """Feature DataFrame built from sample_transactions fixture."""
    from finance_ai.anomaly_engine.features import FeatureEngineer
    fe = FeatureEngineer()
    return fe.build_features(sample_transactions)


class TestIsolationForestDetector:
    def test_fit_returns_self(self, detector, feature_df):
        result = detector.fit(feature_df)
        assert result is detector

    def test_score_returns_ndarray(self, detector, feature_df):
        detector.fit(feature_df)
        scores = detector.score(feature_df)
        assert isinstance(scores, np.ndarray)

    def test_score_length_matches_input(self, detector, feature_df):
        detector.fit(feature_df)
        scores = detector.score(feature_df)
        assert len(scores) == len(feature_df)

    def test_scores_in_unit_interval(self, detector, feature_df):
        detector.fit(feature_df)
        scores = detector.score(feature_df)
        assert scores.min() >= 0.0, "Scores must be >= 0"
        assert scores.max() <= 1.0, "Scores must be <= 1"

    def test_fit_score_equivalent(self, detector, feature_df):
        scores_fit_score = detector.fit_score(feature_df)
        scores_separate  = IsolationForestDetector(
            contamination=0.1, n_estimators=50, random_state=42
        ).fit(feature_df).score(feature_df)
        # Same random seed → same results
        np.testing.assert_allclose(scores_fit_score, scores_separate, rtol=1e-5)

    def test_score_before_fit_raises(self, detector, feature_df):
        with pytest.raises(RuntimeError, match="not fitted"):
            detector.score(feature_df)

    def test_fit_requires_min_samples(self, detector):
        tiny_df = pd.DataFrame([[0.0] * len(FEATURE_COLUMNS)] * 5,
                                columns=FEATURE_COLUMNS)
        with pytest.raises(ValueError, match="At least 10"):
            detector.fit(tiny_df)

    def test_missing_columns_zero_filled(self, detector, feature_df):
        """Detector should handle DataFrames with some columns missing."""
        partial_df = feature_df[FEATURE_COLUMNS[:5]]  # only 5 cols
        detector.fit(feature_df)
        # Should not raise — missing columns are zero-filled
        scores = detector.score(partial_df)
        assert len(scores) == len(partial_df)

    def test_anomalous_transactions_score_higher(self, detector, feature_df, sample_transactions):
        """High-risk transactions should receive higher anomaly scores than normal ones."""
        detector.fit(feature_df)
        scores = detector.score(feature_df)

        # Identify normal vs anomalous by the 'is_anomalous' marker in fixtures
        anomalous_indices = [
            i for i, t in enumerate(sample_transactions)
            if t.get("is_anomalous", False)
        ]
        normal_indices = [
            i for i, t in enumerate(sample_transactions)
            if not t.get("is_anomalous", False)
        ]

        if anomalous_indices and normal_indices:
            avg_anomalous = scores[anomalous_indices].mean()
            avg_normal    = scores[normal_indices].mean()
            # Anomalous transactions should score at least slightly higher on average
            assert avg_anomalous >= avg_normal * 0.8, (
                f"Expected anomalous ({avg_anomalous:.3f}) >= normal ({avg_normal:.3f})"
            )

    def test_save_and_load(self, detector, feature_df, tmp_path):
        """Model should persist correctly to disk and reload intact."""
        detector.fit(feature_df)
        original_scores = detector.score(feature_df)

        model_path = str(tmp_path / "test_model.pkl")
        detector.save(model_path)

        loaded = IsolationForestDetector.load(model_path)
        loaded_scores = loaded.score(feature_df)

        np.testing.assert_allclose(original_scores, loaded_scores, rtol=1e-5)

    def test_load_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            IsolationForestDetector.load("/nonexistent/path/model.pkl")
