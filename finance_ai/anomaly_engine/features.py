"""
FinGuard AI — Feature Engineering
===================================
Transforms raw transaction records (dicts) into a numerical feature
DataFrame suitable for Isolation Forest and other ML models.

All computation is pandas-vectorised; no Frappe dependency.
"""
from __future__ import annotations

import re
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# Account-type → integer mapping
# ---------------------------------------------------------------------------
_ACCOUNT_TYPE_MAP: Dict[str, int] = {
    "payable":                 1,
    "receivable":              2,
    "bank":                    3,
    "cash":                    4,
    "tax":                     5,
    "stock":                   6,
    "fixed asset":             7,
    "expense account":         8,
    "income account":          9,
    "equity":                  10,
    "capital work in progress":11,
    "depreciation":            12,
    "temporary":               13,
    "cost of goods sold":      14,
    "chargeable":              15,
    "accumulated depreciation":16,
    "current asset":           17,
    "current liability":       18,
    "other":                    0,
}

# Columns produced by FeatureEngineer.build_features()
FEATURE_COLUMNS: List[str] = [
    "amount",
    "log_amount",
    "debit_amount",
    "credit_amount",
    "posting_hour",
    "posting_day_of_week",
    "is_weekend",
    "is_off_hours",
    "amount_round_100",
    "amount_round_1000",
    "account_type_code",
    "counterparty_freq",
    "velocity_3d",
    "velocity_7d",
]


def encode_account_type(account_type: str) -> int:
    """Map an ERPNext account type string to an integer code.

    Unknown types map to 0.

    Parameters
    ----------
    account_type:
        String as stored in ERPNext (case-insensitive).

    Returns
    -------
    int
        Integer code in [0, 16].
    """
    if not account_type:
        return 0
    return _ACCOUNT_TYPE_MAP.get(account_type.strip().lower(), 0)


def _parse_datetime(value: Any) -> datetime:
    """Best-effort parse of a date/datetime value."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if value is None:
        return datetime(2000, 1, 1)
    try:
        return pd.to_datetime(str(value)).to_pydatetime()
    except Exception:
        return datetime(2000, 1, 1)


class FeatureEngineer:
    """
    Transform a list of transaction dicts into an ML-ready feature DataFrame.

    Expected keys in each transaction dict
    ---------------------------------------
    name            : str  — unique transaction ID
    posting_date    : str | date | datetime
    creation        : str | datetime  — fallback for hour extraction
    amount          : float
    debit_amount    : float
    credit_amount   : float
    party           : str  — vendor / customer name
    party_type      : str  — 'Supplier' | 'Customer' | etc.
    account_type    : str  — ERPNext account type
    narration       : str  — description / remarks
    company         : str
    """

    def build_features(self, transactions: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Build the feature matrix from a list of transaction dicts.

        Parameters
        ----------
        transactions:
            List of transaction dicts (see class docstring for keys).

        Returns
        -------
        pd.DataFrame
            Rows = transactions, columns = FEATURE_COLUMNS.
            Index matches the order of the input list.
        """
        if not transactions:
            return pd.DataFrame(columns=FEATURE_COLUMNS)

        df = pd.DataFrame(transactions)

        def _col(name: str) -> pd.Series:
            """Return the named column or a zero-filled Series if missing."""
            return df[name] if name in df.columns else pd.Series([0] * len(df), dtype=float)

        # ── monetary amounts ─────────────────────────────────────────────────
        df["amount"]        = pd.to_numeric(_col("amount"),        errors="coerce").fillna(0.0)
        df["debit_amount"]  = pd.to_numeric(_col("debit_amount"),  errors="coerce").fillna(0.0)
        df["credit_amount"] = pd.to_numeric(_col("credit_amount"), errors="coerce").fillna(0.0)

        # If amount is 0 but debit/credit provided, use the larger side
        mask = df["amount"] == 0
        df.loc[mask, "amount"] = df.loc[mask, [
            "debit_amount", "credit_amount"
        ]].abs().max(axis=1)

        df["log_amount"] = np.log1p(df["amount"].abs())

        # ── round-amount flags ───────────────────────────────────────────────
        df["amount_round_100"]  = ((df["amount"] % 100) == 0) & (df["amount"] != 0)
        df["amount_round_1000"] = ((df["amount"] % 1000) == 0) & (df["amount"] != 0)
        df["amount_round_100"]  = df["amount_round_100"].astype(int)
        df["amount_round_1000"] = df["amount_round_1000"].astype(int)

        # ── temporal features ────────────────────────────────────────────────
        # Prefer creation timestamp for hour; fall back to posting_date at noon
        if "creation" in df.columns:
            dt_col = df["creation"]
        elif "posting_date" in df.columns:
            dt_col = df["posting_date"]
        else:
            dt_col = pd.Series([None] * len(df))
        datetimes = (dt_col if dt_col is not None else pd.Series([None] * len(df))).apply(_parse_datetime)

        df["posting_hour"]        = datetimes.apply(lambda d: d.hour)
        df["posting_day_of_week"] = datetimes.apply(lambda d: d.weekday())  # 0=Mon
        df["is_weekend"]          = (df["posting_day_of_week"] >= 5).astype(int)
        df["is_off_hours"]        = ((df["posting_hour"] < 8) | (df["posting_hour"] > 20)).astype(int)

        # ── account type encoding ────────────────────────────────────────────
        acct_series = df["account_type"].fillna("") if "account_type" in df.columns \
                      else pd.Series([""] * len(df))
        df["account_type_code"] = acct_series.apply(encode_account_type)

        # ── counterparty frequency ───────────────────────────────────────────
        party_series = df["party"].fillna("") if "party" in df.columns \
                       else pd.Series([""] * len(df))
        df["counterparty_freq"] = party_series.map(party_series.value_counts())

        # ── velocity (transactions from same party within N days) ────────────
        if "posting_date" in df.columns:
            posting_dates = df["posting_date"].apply(
                lambda v: pd.to_datetime(str(v), errors="coerce")
            )
        else:
            posting_dates = pd.Series([pd.NaT] * len(df))
        df["_posting_dt"] = posting_dates
        df["_party"]      = party_series

        df["velocity_3d"] = self._compute_velocity(df, days=3)
        df["velocity_7d"] = self._compute_velocity(df, days=7)

        # ── select & return ──────────────────────────────────────────────────
        df = df.reindex(columns=FEATURE_COLUMNS, fill_value=0)
        return df.reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _compute_velocity(self, df: pd.DataFrame, days: int) -> pd.Series:
        """
        Count how many transactions share the same party within `days`
        of each transaction's posting date.

        Returns a Series aligned to df.index.
        """
        result = []
        delta  = pd.Timedelta(days=days)

        for i, row in df.iterrows():
            party = row.get("_party", "")
            dt    = row.get("_posting_dt")
            if not party or pd.isna(dt):
                result.append(0)
                continue
            same_party = df["_party"] == party
            near_date  = (df["_posting_dt"] - dt).abs() <= delta
            count      = int((same_party & near_date).sum()) - 1  # exclude self
            result.append(max(count, 0))

        return pd.Series(result, index=df.index)
