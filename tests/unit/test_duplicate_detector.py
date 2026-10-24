"""
FinGuard AI — Unit Tests: DuplicateDetector
============================================
"""
from __future__ import annotations

import pytest
from finance_ai.anomaly_engine.duplicate_detector import DuplicateDetector


@pytest.fixture
def detector():
    return DuplicateDetector(similarity_threshold=85, date_window_days=3)


@pytest.fixture
def base_txn():
    return {
        "name":         "JE-001",
        "party":        "Vendor ABC",
        "amount":       50_000.0,
        "posting_date": "2024-03-15",
        "narration":    "Invoice payment march 2024",
    }


class TestNormalization:
    def test_normalize_removes_punctuation(self, detector):
        result = detector._normalize_narration("Invoice #1234 — payment!")
        assert "#" not in result and "—" not in result and "!" not in result

    def test_normalize_lowercases(self, detector):
        result = detector._normalize_narration("INVOICE PAYMENT MARCH")
        assert result == result.lower()

    def test_normalize_collapses_whitespace(self, detector):
        result = detector._normalize_narration("invoice   payment  march")
        assert "  " not in result


class TestIsDuplicate:
    def test_exact_duplicate_detected(self, detector, base_txn):
        other = dict(base_txn, name="JE-002")
        is_dup, sim, reason = detector.is_duplicate(base_txn, other)
        assert is_dup is True
        assert sim >= 85
        assert reason != ""

    def test_fuzzy_narration_duplicate_detected(self, detector, base_txn):
        other = dict(base_txn, name="JE-003",
                     narration="Invoice Payment March-2024")  # slight variation
        is_dup, sim, _ = detector.is_duplicate(base_txn, other)
        assert is_dup is True
        assert sim >= 85

    def test_different_amount_not_duplicate(self, detector, base_txn):
        other = dict(base_txn, name="JE-004", amount=99_000.0)
        is_dup, _, _ = detector.is_duplicate(base_txn, other)
        assert is_dup is False

    def test_different_party_not_duplicate(self, detector, base_txn):
        other = dict(base_txn, name="JE-005", party="Different Vendor")
        is_dup, _, _ = detector.is_duplicate(base_txn, other)
        assert is_dup is False

    def test_date_outside_window_not_duplicate(self, detector, base_txn):
        other = dict(base_txn, name="JE-006", posting_date="2024-03-25")
        is_dup, _, _ = detector.is_duplicate(base_txn, other)
        assert is_dup is False

    def test_completely_different_narration_not_duplicate(self, detector, base_txn):
        other = dict(base_txn, name="JE-007",
                     narration="Staff salary disbursement payroll run")
        is_dup, sim, _ = detector.is_duplicate(base_txn, other)
        assert is_dup is False


class TestFindDuplicates:
    def test_finds_duplicate_in_batch(self, detector, base_txn):
        txns = [
            base_txn,
            dict(base_txn, name="JE-DUP", narration="Invoice payment march 2024 copy"),
            {"name": "JE-NORMAL", "party": "Other Vendor",
             "amount": 12_345.0, "posting_date": "2024-03-15",
             "narration": "Office supplies purchase"},
        ]
        results = detector.find_duplicates(txns)
        assert len(results) >= 1
        assert any(r["transaction_id"] == "JE-DUP" for r in results)

    def test_empty_list_returns_empty(self, detector):
        assert detector.find_duplicates([]) == []

    def test_single_transaction_no_duplicates(self, detector, base_txn):
        assert detector.find_duplicates([base_txn]) == []
