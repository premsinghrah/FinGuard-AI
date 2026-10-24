"""
FinGuard AI — Unit Tests: FeatureEngineer
==========================================
Tests run without any Frappe dependency.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from finance_ai.anomaly_engine.features import FeatureEngineer, encode_account_type, FEATURE_COLUMNS


class TestEncodeAccountType:
    def test_known_type_returns_nonzero_code(self):
        assert encode_account_type("Bank") != 0
        assert encode_account_type("Payable") != 0

    def test_case_insensitive(self):
        assert encode_account_type("BANK") == encode_account_type("bank")

    def test_unknown_type_returns_zero(self):
        assert encode_account_type("XYZ Unknown Type") == 0

    def test_none_returns_zero(self):
        assert encode_account_type(None) == 0  # type: ignore[arg-type]

    def test_empty_string_returns_zero(self):
        assert encode_account_type("") == 0


class TestFeatureEngineer:
    @pytest.fixture
    def fe(self):
        return FeatureEngineer()

    @pytest.fixture
    def single_txn(self):
        return [{
            "name": "JE-001",
            "posting_date": "2024-03-15",
            "creation": "2024-03-15 23:47:00",
            "amount": 100_000.0,
            "debit_amount": 100_000.0,
            "credit_amount": 0.0,
            "party": "Vendor ABC",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "March rent payment",
            "company": "Test Co",
        }]

    def test_build_features_returns_dataframe(self, fe, sample_transactions):
        """build_features must return a pandas DataFrame."""
        df = fe.build_features(sample_transactions)
        assert isinstance(df, pd.DataFrame)

    def test_output_has_expected_columns(self, fe, sample_transactions):
        """All FEATURE_COLUMNS must be present in the output."""
        df = fe.build_features(sample_transactions)
        for col in FEATURE_COLUMNS:
            assert col in df.columns, f"Missing column: {col}"

    def test_row_count_matches_input(self, fe, sample_transactions):
        """One output row per input transaction."""
        df = fe.build_features(sample_transactions)
        assert len(df) == len(sample_transactions)

    def test_log_amount_computed_correctly(self, fe, single_txn):
        """log_amount should equal log1p(amount)."""
        df = fe.build_features(single_txn)
        expected = math.log1p(100_000.0)
        assert abs(df["log_amount"].iloc[0] - expected) < 1e-6

    def test_is_off_hours_flag_night(self, fe):
        """Transactions posted at 23:47 should be flagged as off-hours."""
        txn = [{
            "name": "JE-002",
            "posting_date": "2024-03-15",
            "creation": "2024-03-15 23:47:00",
            "amount": 5000.0,
            "party": "Vendor X",
        }]
        df = fe.build_features(txn)
        assert df["is_off_hours"].iloc[0] == 1

    def test_is_off_hours_flag_business_hours(self, fe):
        """Transactions posted at 10:00 should NOT be off-hours."""
        txn = [{
            "name": "JE-003",
            "posting_date": "2024-03-15",
            "creation": "2024-03-15 10:00:00",
            "amount": 5000.0,
            "party": "Vendor X",
        }]
        df = fe.build_features(txn)
        assert df["is_off_hours"].iloc[0] == 0

    def test_is_weekend_flag_saturday(self, fe):
        """2024-03-16 is a Saturday — should be flagged."""
        txn = [{
            "name": "JE-004",
            "posting_date": "2024-03-16",
            "creation": "2024-03-16 09:00:00",
            "amount": 5000.0,
            "party": "Vendor X",
        }]
        df = fe.build_features(txn)
        assert df["is_weekend"].iloc[0] == 1

    def test_round_amount_1000_detected(self, fe):
        """Amount exactly divisible by 1000 should set amount_round_1000=1."""
        txn = [{
            "name": "JE-005",
            "posting_date": "2024-03-15",
            "creation": "2024-03-15 11:00:00",
            "amount": 50_000.0,
            "party": "Vendor X",
        }]
        df = fe.build_features(txn)
        assert df["amount_round_1000"].iloc[0] == 1

    def test_non_round_amount_not_flagged(self, fe):
        """Amount not divisible by 1000 should leave amount_round_1000=0."""
        txn = [{
            "name": "JE-006",
            "posting_date": "2024-03-15",
            "creation": "2024-03-15 11:00:00",
            "amount": 50_123.45,
            "party": "Vendor X",
        }]
        df = fe.build_features(txn)
        assert df["amount_round_1000"].iloc[0] == 0

    def test_counterparty_frequency_multiple_txns(self, fe):
        """Same party appearing N times should have counterparty_freq=N."""
        txns = [
            {"name": f"JE-00{i}", "posting_date": "2024-03-15",
             "creation": "2024-03-15 10:00:00", "amount": 1000,
             "party": "Frequent Vendor"}
            for i in range(5)
        ]
        df = fe.build_features(txns)
        assert (df["counterparty_freq"] == 5).all()

    def test_velocity_3d_increases_for_clustered_txns(self, fe):
        """Transactions from the same party on consecutive days should show velocity > 0."""
        base = datetime(2024, 3, 15, 10, 0, 0)
        txns = [
            {
                "name": f"JE-V{i}",
                "posting_date": str((base + timedelta(days=i)).date()),
                "creation":     str(base + timedelta(days=i)),
                "amount": 1000.0,
                "party": "Cluster Vendor",
            }
            for i in range(4)
        ]
        df = fe.build_features(txns)
        # Middle transactions should show velocity > 0 (nearby neighbors exist)
        assert df["velocity_3d"].max() > 0

    def test_missing_values_handled(self, fe):
        """Transactions with missing fields should not raise exceptions."""
        txns = [{"name": "JE-EMPTY"}]  # all optional fields missing
        df = fe.build_features(txns)
        assert len(df) == 1
        assert not df.isnull().any().any(), "No NaN values should remain"

    def test_empty_transactions_list(self, fe):
        """Empty input should return an empty DataFrame with correct columns."""
        df = fe.build_features([])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        for col in FEATURE_COLUMNS:
            assert col in df.columns
