"""
FinGuard AI — Pytest Fixtures (conftest.py)
===========================================

Shared fixtures used across all test modules.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Transaction data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_transactions() -> List[Dict[str, Any]]:
    """
    Return 20 realistic transaction dicts simulating Journal Entry rows.

    Mix includes:
    - Normal business transactions (low risk)
    - Round-amount transactions (suspicious)
    - Off-hours transactions (suspicious)
    - Weekend transactions (suspicious)
    - Exact and near-duplicate pairs
    - Very large amounts
    - Zero-amount entries
    - Negative amounts
    """
    base_date = datetime(2024, 3, 15)  # Friday

    records = [
        # ── Normal transactions ─────────────────────────────────────────
        {
            "name": "JE-0001",
            "posting_date": base_date.date(),
            "amount": 12_543.75,
            "debit_amount": 12_543.75,
            "credit_amount": 0.0,
            "party": "Acme Corp",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Office supplies purchase Q1",
            "creation": datetime(2024, 3, 15, 10, 30, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0002",
            "posting_date": base_date.date(),
            "amount": 8_750.50,
            "debit_amount": 8_750.50,
            "credit_amount": 0.0,
            "party": "Global Traders",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Raw material procurement invoice #INV-2024-003",
            "creation": datetime(2024, 3, 15, 11, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0003",
            "posting_date": base_date.date(),
            "amount": 3_299.00,
            "debit_amount": 3_299.00,
            "credit_amount": 0.0,
            "party": "City Electricals",
            "party_type": "Supplier",
            "account_type": "Expense",
            "narration": "Electricity bill February 2024",
            "creation": datetime(2024, 3, 15, 14, 15, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0004",
            "posting_date": base_date.date(),
            "amount": 45_000.00,
            "debit_amount": 45_000.00,
            "credit_amount": 0.0,
            "party": "Employee A",
            "party_type": "Employee",
            "account_type": "Expense",
            "narration": "March salary advance — Employee A, Staff ID EMP-042",
            "creation": datetime(2024, 3, 15, 9, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0005",
            "posting_date": base_date.date(),
            "amount": 1_875.25,
            "debit_amount": 1_875.25,
            "credit_amount": 0.0,
            "party": "FastCourier Ltd",
            "party_type": "Supplier",
            "account_type": "Expense",
            "narration": "Courier and logistics charges Feb 2024",
            "creation": datetime(2024, 3, 15, 15, 45, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Round-amount suspicious transactions ────────────────────────
        {
            "name": "JE-0006",
            "posting_date": base_date.date(),
            "amount": 100_000.00,
            "debit_amount": 100_000.00,
            "credit_amount": 0.0,
            "party": "Shadowy Ventures",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Consultancy fees",
            "creation": datetime(2024, 3, 15, 22, 0, 0),  # off-hours too
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0007",
            "posting_date": base_date.date(),
            "amount": 500_000.00,
            "debit_amount": 500_000.00,
            "credit_amount": 0.0,
            "party": "New Entity XYZ",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Advisory services",
            "creation": datetime(2024, 3, 16, 2, 30, 0),  # midnight/off-hours
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Weekend transaction ──────────────────────────────────────────
        {
            "name": "JE-0008",
            "posting_date": datetime(2024, 3, 16).date(),  # Saturday
            "amount": 75_000.00,
            "debit_amount": 75_000.00,
            "credit_amount": 0.0,
            "party": "Weekend Supplier",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Urgent payment weekend",
            "creation": datetime(2024, 3, 16, 11, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Duplicate pair ───────────────────────────────────────────────
        {
            "name": "JE-0009",
            "posting_date": base_date.date(),
            "amount": 22_500.00,
            "debit_amount": 22_500.00,
            "credit_amount": 0.0,
            "party": "Acme Corp",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Monthly retainer payment Acme Corp",
            "creation": datetime(2024, 3, 15, 10, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0010",
            "posting_date": base_date.date(),
            "amount": 22_500.00,
            "debit_amount": 22_500.00,
            "credit_amount": 0.0,
            "party": "Acme Corp",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Monthly retainer payment Acme Corp",  # exact duplicate
            "creation": datetime(2024, 3, 15, 10, 5, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Near-duplicate (fuzzy narration) ─────────────────────────────
        {
            "name": "JE-0011",
            "posting_date": base_date.date(),
            "amount": 15_000.00,
            "debit_amount": 15_000.00,
            "credit_amount": 0.0,
            "party": "Global Traders",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Invoice INV-2024-007 payment",
            "creation": datetime(2024, 3, 15, 12, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0012",
            "posting_date": (base_date + timedelta(days=1)).date(),
            "amount": 15_000.00,
            "debit_amount": 15_000.00,
            "credit_amount": 0.0,
            "party": "Global Traders",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Invoice INV-2024-007 payment duplicate",  # fuzzy near-dup
            "creation": datetime(2024, 3, 16, 9, 30, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Zero-amount ──────────────────────────────────────────────────
        {
            "name": "JE-0013",
            "posting_date": base_date.date(),
            "amount": 0.0,
            "debit_amount": 0.0,
            "credit_amount": 0.0,
            "party": "Internal Dept",
            "party_type": "Customer",
            "account_type": "Income",
            "narration": "Zero adjustment entry",
            "creation": datetime(2024, 3, 15, 13, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Negative amount ──────────────────────────────────────────────
        {
            "name": "JE-0014",
            "posting_date": base_date.date(),
            "amount": -5_000.00,
            "debit_amount": 0.0,
            "credit_amount": 5_000.00,
            "party": "Returns Party",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Credit note reversal",
            "creation": datetime(2024, 3, 15, 16, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Very large amount ────────────────────────────────────────────
        {
            "name": "JE-0015",
            "posting_date": base_date.date(),
            "amount": 2_500_000.00,
            "debit_amount": 2_500_000.00,
            "credit_amount": 0.0,
            "party": "Mega Supplier",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Capital equipment purchase — machinery",
            "creation": datetime(2024, 3, 15, 10, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── High-frequency same party ─────────────────────────────────
        {
            "name": "JE-0016",
            "posting_date": base_date.date(),
            "amount": 9_999.00,
            "debit_amount": 9_999.00,
            "credit_amount": 0.0,
            "party": "Quick Payments Ltd",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Recurring service charge batch 1",
            "creation": datetime(2024, 3, 15, 8, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0017",
            "posting_date": base_date.date(),
            "amount": 9_999.00,
            "debit_amount": 9_999.00,
            "credit_amount": 0.0,
            "party": "Quick Payments Ltd",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Recurring service charge batch 2",
            "creation": datetime(2024, 3, 15, 8, 30, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0018",
            "posting_date": base_date.date(),
            "amount": 9_999.00,
            "debit_amount": 9_999.00,
            "credit_amount": 0.0,
            "party": "Quick Payments Ltd",
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": "Recurring service charge batch 3",
            "creation": datetime(2024, 3, 15, 9, 0, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        # ── Normal — misc ─────────────────────────────────────────────
        {
            "name": "JE-0019",
            "posting_date": base_date.date(),
            "amount": 6_732.00,
            "debit_amount": 6_732.00,
            "credit_amount": 0.0,
            "party": "Telecom Services",
            "party_type": "Supplier",
            "account_type": "Expense",
            "narration": "Internet and telephone bill March 2024",
            "creation": datetime(2024, 3, 15, 11, 30, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
        {
            "name": "JE-0020",
            "posting_date": base_date.date(),
            "amount": 18_450.00,
            "debit_amount": 18_450.00,
            "credit_amount": 0.0,
            "party": "Office Rent Co",
            "party_type": "Supplier",
            "account_type": "Expense",
            "narration": "March 2024 office rent — Floor 3",
            "creation": datetime(2024, 3, 15, 9, 15, 0),
            "company": "Test Company",
            "doctype": "Journal Entry",
        },
    ]

    return records


@pytest.fixture(scope="session")
def transaction_df(sample_transactions: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Return a pandas DataFrame built from the sample_transactions fixture.

    The creation column is kept as datetime objects; posting_date as date.
    """
    df = pd.DataFrame(sample_transactions)
    df["posting_date"] = pd.to_datetime(df["posting_date"])
    df["creation"] = pd.to_datetime(df["creation"])
    return df


@pytest.fixture(scope="session")
def rule_config() -> Dict[str, Any]:
    """
    Return a configuration dict compatible with RuleEngine.

    Uses conservative but realistic threshold values that exercise
    multiple rules against the sample_transactions fixture.
    """
    return {
        "large_amount_threshold": 500_000,      # Triggers for JE-0007, JE-0015
        "round_amount_threshold": 1_000,        # Any amount divisible by 1000
        "off_hours_start": 20,                  # 8 PM — post this is off-hours
        "off_hours_end": 6,                     # 6 AM — before this is off-hours
        "high_velocity_threshold": 5,           # 5+ transactions per party/day
        "zero_amount_flag": True,
        "negative_amount_flag": True,
        "weekend_flag": True,
        "max_duplicate_window_days": 3,
        "duplicate_amount_tolerance": 0.01,     # 1% tolerance
        "min_narration_similarity": 85,         # fuzzy match threshold (%)
        "anomaly_threshold": 0.6,
        "ml_weight": 40,
        "rule_weight": 40,
        "duplicate_weight": 20,
        "high_risk_threshold": 0.75,
        "medium_risk_threshold": 0.5,
        "critical_risk_threshold": 0.90,
    }
