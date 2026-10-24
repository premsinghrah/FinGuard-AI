"""
FinGuard AI — Unit Tests: AnomalyScorer
=========================================
"""
import pytest
from finance_ai.anomaly_engine.scorer import AnomalyScorer


class TestAnomalyScorer:
    def test_default_weights_sum_to_100(self):
        scorer = AnomalyScorer()
        assert scorer.ml_weight + scorer.rule_weight + scorer.duplicate_weight == 100

    def test_weights_must_sum_to_100(self):
        with pytest.raises(ValueError, match="sum to 100"):
            AnomalyScorer(ml_weight=50, rule_weight=50, duplicate_weight=10)

    def test_composite_score_weighted_correctly(self):
        scorer = AnomalyScorer(ml_weight=40, rule_weight=35, duplicate_weight=25)
        score = scorer.composite_score(ml_score=0.8, rule_score=0.6, duplicate_score=1.0)
        expected = (0.8 * 40 + 0.6 * 35 + 1.0 * 25) / 100
        assert abs(score - expected) < 1e-6

    def test_score_clamped_to_unit_interval_low(self):
        scorer = AnomalyScorer()
        score = scorer.composite_score(-0.5, -0.5, 0.0)
        assert score >= 0.0

    def test_score_clamped_to_unit_interval_high(self):
        scorer = AnomalyScorer()
        score = scorer.composite_score(2.0, 2.0, 2.0)
        assert score <= 1.0

    def test_high_risk_classification(self):
        scorer = AnomalyScorer()
        assert scorer.classify(0.90) == "High Risk"
        assert scorer.classify(0.75) == "High Risk"

    def test_medium_risk_classification(self):
        scorer = AnomalyScorer()
        assert scorer.classify(0.60) == "Medium Risk"
        assert scorer.classify(0.45) == "Medium Risk"

    def test_low_risk_classification(self):
        scorer = AnomalyScorer()
        assert scorer.classify(0.20) == "Low Risk"
        assert scorer.classify(0.0) == "Low Risk"

    def test_custom_thresholds_respected(self):
        scorer = AnomalyScorer()
        assert scorer.classify(0.60, high_threshold=0.50) == "High Risk"
        assert scorer.classify(0.30, medium_threshold=0.20) == "Medium Risk"

    def test_zero_scores_give_low_risk(self):
        scorer = AnomalyScorer()
        score = scorer.composite_score(0.0, 0.0, 0.0)
        assert score == 0.0
        assert scorer.classify(score) == "Low Risk"

    def test_all_ones_give_high_risk(self):
        scorer = AnomalyScorer()
        score = scorer.composite_score(1.0, 1.0, 1.0)
        assert score == 1.0
        assert scorer.classify(score) == "High Risk"
