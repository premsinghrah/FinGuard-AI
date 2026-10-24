"""
FinGuard AI — Unit Tests: RuleEngine
======================================
Tests run without any Frappe dependency.
"""
from __future__ import annotations

import pytest
from finance_ai.anomaly_engine.rule_engine import RuleEngine


@pytest.fixture
def engine():
    return RuleEngine()


@pytest.fixture
def normal_txn():
    """A perfectly normal transaction that should trigger no rules."""
    return {
        "name":                  "JE-NORMAL",
        "amount":                75_432.50,
        "debit_amount":          75_432.50,
        "credit_amount":         0.0,
        "posting_hour":          11,
        "posting_day_of_week":   2,   # Wednesday
        "party":                 "Vendor ABC",
        "debit_party":           "Vendor ABC",
        "credit_party":          "Cash Account",
        "account_type":          "Payable",
        "debit_account_type":    "Payable",
        "credit_account_type":   "Bank",
        "narration":             "March office supply invoice #INV-1234",
        "velocity_3d":           1,
    }


class TestRoundAmountRule:
    def test_round_1000_triggers(self, engine):
        txn = {"amount": 100_000, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Valid payment narration here"}
        rules = engine.check(txn)
        assert "ROUND_AMOUNT" in rules

    def test_non_round_does_not_trigger(self, engine, normal_txn):
        rules = engine.check(normal_txn)
        assert "ROUND_AMOUNT" not in rules


class TestLargeAmountRule:
    def test_above_threshold_triggers(self, engine):
        txn = {"amount": 600_000, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Large vendor payment authorised"}
        rules = engine.check(txn)
        assert "LARGE_AMOUNT" in rules

    def test_custom_threshold_respected(self):
        engine = RuleEngine(config={"large_amount_threshold": 1_000_000})
        txn = {"amount": 600_000, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Payment below custom threshold"}
        rules = engine.check(txn)
        assert "LARGE_AMOUNT" not in rules


class TestOffHoursRule:
    def test_night_hour_triggers(self, engine):
        txn = {"amount": 10_000, "posting_hour": 23, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Night posting test"}
        rules = engine.check(txn)
        assert "OFF_HOURS_POSTING" in rules

    def test_early_morning_triggers(self, engine):
        txn = {"amount": 10_000, "posting_hour": 5, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Early morning posting test"}
        rules = engine.check(txn)
        assert "OFF_HOURS_POSTING" in rules

    def test_business_hours_no_trigger(self, engine, normal_txn):
        rules = engine.check(normal_txn)
        assert "OFF_HOURS_POSTING" not in rules


class TestWeekendRule:
    def test_saturday_triggers(self, engine):
        txn = {"amount": 10_000, "posting_hour": 10, "posting_day_of_week": 5,
               "velocity_3d": 0, "narration": "Weekend posting saturday"}
        rules = engine.check(txn)
        assert "WEEKEND_POSTING" in rules

    def test_sunday_triggers(self, engine):
        txn = {"amount": 10_000, "posting_hour": 10, "posting_day_of_week": 6,
               "velocity_3d": 0, "narration": "Weekend posting sunday"}
        rules = engine.check(txn)
        assert "WEEKEND_POSTING" in rules

    def test_weekday_no_trigger(self, engine, normal_txn):
        rules = engine.check(normal_txn)
        assert "WEEKEND_POSTING" not in rules


class TestZeroAndNegativeRules:
    def test_zero_amount_triggers(self, engine):
        txn = {"amount": 0, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Zero amount posting"}
        assert "ZERO_AMOUNT" in engine.check(txn)

    def test_negative_amount_triggers(self, engine):
        txn = {"amount": -5000, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Negative amount posting"}
        assert "NEGATIVE_AMOUNT" in engine.check(txn)


class TestVelocityRule:
    def test_high_velocity_triggers(self, engine):
        txn = {"amount": 10_000, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 8, "narration": "High velocity vendor"}
        assert "HIGH_VELOCITY_3D" in engine.check(txn)

    def test_low_velocity_no_trigger(self, engine, normal_txn):
        normal_txn["velocity_3d"] = 2
        assert "HIGH_VELOCITY_3D" not in engine.check(normal_txn)


class TestMissingNarrationRule:
    def test_empty_narration_triggers(self, engine):
        txn = {"amount": 5000, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": ""}
        assert "MISSING_NARRATION" in engine.check(txn)

    def test_short_narration_triggers(self, engine):
        txn = {"amount": 5000, "posting_hour": 10, "posting_day_of_week": 1,
               "velocity_3d": 0, "narration": "Pay"}
        assert "MISSING_NARRATION" in engine.check(txn)


class TestNormalTransaction:
    def test_no_rules_triggered_for_normal_transaction(self, engine, normal_txn):
        """A well-formed, in-hours, weekday transaction should trigger no rules."""
        rules = engine.check(normal_txn)
        # Only ROUND_AMOUNT is possible if amount happens to be divisible by 1000
        suspicious = [r for r in rules if r not in ("ROUND_AMOUNT",)]
        assert suspicious == [], f"Unexpected rules triggered: {suspicious}"

    def test_multiple_rules_can_trigger(self, engine):
        """A single problematic transaction can trigger multiple rules."""
        txn = {
            "amount": 0,           # ZERO_AMOUNT
            "posting_hour": 23,    # OFF_HOURS_POSTING
            "posting_day_of_week": 6,  # WEEKEND_POSTING
            "velocity_3d": 0,
            "narration": "",       # MISSING_NARRATION
        }
        rules = engine.check(txn)
        assert len(rules) >= 3

    def test_rule_score_increases_with_more_rules(self, engine):
        """More triggered rules should produce a higher rule_score."""
        score_0 = engine.rule_score([])
        score_1 = engine.rule_score(["ROUND_AMOUNT"])
        score_3 = engine.rule_score(["ROUND_AMOUNT", "OFF_HOURS_POSTING", "WEEKEND_POSTING"])
        assert score_0 == 0.0
        assert score_1 > score_0
        assert score_3 > score_1

    def test_rule_score_bounded_to_unit_interval(self, engine):
        """rule_score must always be in [0, 1]."""
        from finance_ai.anomaly_engine.rule_engine import RULE_CODES
        score = engine.rule_score(RULE_CODES)
        assert 0.0 <= score <= 1.0
