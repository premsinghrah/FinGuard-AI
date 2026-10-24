"""
FinGuard AI — Unit Tests: AnomalyExplainer
============================================
"""
import pytest
from finance_ai.anomaly_engine.explainer import AnomalyExplainer, format_amount


class TestFormatAmount:
    def test_crore_formatting(self):
        assert "Cr" in format_amount(25_000_000)

    def test_lakh_formatting(self):
        assert "L" in format_amount(1_500_000)

    def test_small_amount_has_rupee_symbol(self):
        result = format_amount(45_000)
        assert "₹" in result

    def test_negative_amount(self):
        result = format_amount(-100_000)
        assert "-" in result and "₹" in result

    def test_zero_amount(self):
        assert "₹0" in format_amount(0)

    def test_invalid_amount_graceful(self):
        result = format_amount(None)
        assert "₹" in result


class TestAnomalyExplainer:
    @pytest.fixture
    def explainer(self):
        return AnomalyExplainer()

    @pytest.fixture
    def high_risk_txn(self):
        return {
            "name": "JE-TEST-001",
            "source_doctype": "Journal Entry",
            "amount": 500_000.0,
            "party": "Suspicious Vendor",
            "posting_date": "2024-03-16",
            "posting_hour": 23,
            "narration": "",
        }

    def test_high_risk_explanation_returned(self, explainer, high_risk_txn):
        result = explainer.explain(
            transaction=high_risk_txn,
            composite_score=0.85,
            triggered_rules=["ROUND_AMOUNT", "OFF_HOURS_POSTING"],
            is_duplicate=False,
        )
        assert result["risk_level"] == "High Risk"
        assert isinstance(result["summary"], str) and len(result["summary"]) > 0
        assert isinstance(result["reasons"], list) and len(result["reasons"]) > 0
        assert isinstance(result["recommendation"], str) and len(result["recommendation"]) > 0

    def test_medium_risk_classification(self, explainer, high_risk_txn):
        result = explainer.explain(
            transaction=high_risk_txn,
            composite_score=0.55,
            triggered_rules=["WEEKEND_POSTING"],
            is_duplicate=False,
        )
        assert result["risk_level"] == "Medium Risk"

    def test_low_risk_classification(self, explainer, high_risk_txn):
        result = explainer.explain(
            transaction=high_risk_txn,
            composite_score=0.20,
            triggered_rules=[],
            is_duplicate=False,
        )
        assert result["risk_level"] == "Low Risk"

    def test_duplicate_reason_included_in_reasons(self, explainer, high_risk_txn):
        result = explainer.explain(
            transaction=high_risk_txn,
            composite_score=0.80,
            triggered_rules=[],
            is_duplicate=True,
            duplicate_reason="Same vendor, same amount, 1 day apart.",
        )
        reasons_text = " ".join(result["reasons"])
        assert "duplicate" in reasons_text.lower() or "Same vendor" in reasons_text

    def test_rule_codes_translated_to_text(self, explainer, high_risk_txn):
        """Rule codes should be converted to human-readable strings in reasons."""
        result = explainer.explain(
            transaction=high_risk_txn,
            composite_score=0.75,
            triggered_rules=["ROUND_AMOUNT", "OFF_HOURS_POSTING"],
            is_duplicate=False,
        )
        # Should NOT contain raw rule codes in reasons list
        for reason in result["reasons"]:
            assert "ROUND_AMOUNT" not in reason, "Raw rule code should be translated"
            assert "OFF_HOURS_POSTING" not in reason, "Raw rule code should be translated"

    def test_recommendation_not_empty(self, explainer, high_risk_txn):
        result = explainer.explain(
            transaction=high_risk_txn,
            composite_score=0.90,
            triggered_rules=["SELF_TRANSFER"],
            is_duplicate=False,
        )
        assert result["recommendation"].strip() != ""

    def test_summary_contains_party_name(self, explainer, high_risk_txn):
        result = explainer.explain(
            transaction=high_risk_txn,
            composite_score=0.80,
            triggered_rules=["LARGE_AMOUNT"],
            is_duplicate=False,
        )
        assert "Suspicious Vendor" in result["summary"]
