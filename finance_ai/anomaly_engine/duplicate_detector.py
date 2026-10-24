"""
FinGuard AI — Duplicate Transaction Detector
=============================================
Identifies near-duplicate invoices and payments using fuzzy string
matching on narration combined with amount and party matching.

Uses RapidFuzz for fast string similarity — no Frappe dependency.
"""
from __future__ import annotations

import re
import string
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

# Minimum narration similarity to flag as duplicate (overridable)
DEFAULT_SIMILARITY_THRESHOLD = 85.0
# Date window (days) within which to search for duplicates
DEFAULT_DATE_WINDOW_DAYS = 3


class DuplicateDetector:
    """
    Detect near-duplicate financial transactions.

    A transaction B is considered a potential duplicate of transaction A if:
    1. They share the same ``party`` (vendor / customer).
    2. Their ``amount`` values differ by ≤ 0.01 (absolute tolerance).
    3. Their ``posting_date`` values are within ``date_window_days`` of each other.
    4. Their ``narration`` values have a fuzzy similarity ≥ ``similarity_threshold``.

    Conditions 1, 2, and 3 are fast filters applied before the fuzzy step.

    Parameters
    ----------
    similarity_threshold:
        Minimum token-sort ratio (0–100) to flag as duplicate.
    date_window_days:
        Maximum number of days between two transactions for them
        to be considered temporal neighbours.
    """

    def __init__(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.date_window_days     = date_window_days
        self._date_delta          = pd.Timedelta(days=date_window_days)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def find_duplicates(
        self, transactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Scan all transactions and return a list of potential duplicates.

        Parameters
        ----------
        transactions:
            List of transaction dicts.  Expected keys:
              name, party, amount, posting_date, narration.

        Returns
        -------
        list[dict]
            Each dict describes one duplicate relationship::

                {
                    "transaction_id": <name of the flagged transaction>,
                    "duplicate_of":   <name of the earlier transaction>,
                    "similarity":     <float 0–100>,
                    "reason":         <human-readable reason string>,
                }

            Only one entry per pair is returned (the later transaction
            is flagged as the potential duplicate of the earlier one).
        """
        if not transactions:
            return []

        # Pre-process into a DataFrame for fast filtering
        df = pd.DataFrame(transactions)
        df["_pd"]  = pd.to_datetime(df.get("posting_date", None), errors="coerce")
        df["_amt"] = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0.0).abs()
        df["_party"] = df.get("party", pd.Series([""] * len(df))).fillna("").str.strip().str.lower()
        df["_narr"]  = df.get("narration", pd.Series([""] * len(df))).apply(self._normalize_narration)

        results: List[Dict[str, Any]] = []
        seen_pairs: set = set()

        records = df.to_dict("records")

        for i, row_i in enumerate(records):
            for j, row_j in enumerate(records):
                if j <= i:
                    continue  # check each pair once; j is always "later" row

                pair_key = (row_i.get("name"), row_j.get("name"))
                if pair_key in seen_pairs:
                    continue

                is_dup, sim, reason = self.is_duplicate(row_i, row_j)
                if is_dup:
                    seen_pairs.add(pair_key)
                    results.append({
                        "transaction_id": row_j.get("name", f"row_{j}"),
                        "duplicate_of":   row_i.get("name", f"row_{i}"),
                        "similarity":     round(sim, 2),
                        "reason":         reason,
                    })

        return results

    def is_duplicate(
        self,
        t1: Dict[str, Any],
        t2: Dict[str, Any],
    ) -> Tuple[bool, float, str]:
        """
        Check whether two individual transactions are near-duplicates.

        Parameters
        ----------
        t1, t2:
            Transaction dicts (may be raw or pre-processed rows).

        Returns
        -------
        tuple[bool, float, str]
            (is_duplicate, similarity_score_0_to_100, reason_string)
        """
        # ── 1. party match ───────────────────────────────────────────────
        p1 = str(t1.get("_party", t1.get("party", "") or "")).strip().lower()
        p2 = str(t2.get("_party", t2.get("party", "") or "")).strip().lower()
        if not p1 or not p2 or p1 != p2:
            return False, 0.0, ""

        # ── 2. amount proximity ──────────────────────────────────────────
        a1 = abs(float(t1.get("_amt", t1.get("amount", 0) or 0)))
        a2 = abs(float(t2.get("_amt", t2.get("amount", 0) or 0)))
        if abs(a1 - a2) > 0.01:
            return False, 0.0, ""

        # ── 3. date proximity ────────────────────────────────────────────
        d1 = t1.get("_pd") or pd.to_datetime(str(t1.get("posting_date", "")), errors="coerce")
        d2 = t2.get("_pd") or pd.to_datetime(str(t2.get("posting_date", "")), errors="coerce")
        if pd.isna(d1) or pd.isna(d2):
            return False, 0.0, ""
        if abs((d1 - d2).days) > self.date_window_days:
            return False, 0.0, ""

        # ── 4. narration similarity ──────────────────────────────────────
        n1 = t1.get("_narr") or self._normalize_narration(str(t1.get("narration", "") or ""))
        n2 = t2.get("_narr") or self._normalize_narration(str(t2.get("narration", "") or ""))

        similarity = self._fuzzy_ratio(n1, n2)

        if similarity < self.similarity_threshold:
            return False, similarity, ""

        reason = (
            f"Same party '{t1.get('party', 'unknown')}', "
            f"same amount ₹{a1:,.2f}, "
            f"posting dates within {abs((d1-d2).days)} day(s), "
            f"narration similarity {similarity:.1f}%."
        )
        return True, similarity, reason

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _normalize_narration(self, text: str) -> str:
        """
        Lowercase, strip punctuation (ASCII + Unicode), and normalise whitespace.

        This makes fuzzy matching more robust to minor formatting
        differences (e.g., "Invoice #1234" vs "invoice 1234").
        """
        if not text:
            return ""
        import unicodedata
        text = text.lower()
        # Normalise Unicode (decompose accented chars etc.)
        text = unicodedata.normalize("NFKD", text)
        # Strip ASCII punctuation
        text = re.sub(r"[" + re.escape(string.punctuation) + r"]", " ", text)
        # Strip remaining non-alphanumeric Unicode characters (em-dash, smart quotes…)
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _fuzzy_ratio(self, a: str, b: str) -> float:
        """Return token_sort_ratio (0–100) between two strings."""
        if not a and not b:
            return 100.0
        if not _HAS_RAPIDFUZZ:
            # Fallback: simple character-level ratio
            longer  = max(len(a), len(b))
            if longer == 0:
                return 100.0
            common  = sum(c1 == c2 for c1, c2 in zip(a, b))
            return round((common / longer) * 100, 2)
        return fuzz.token_sort_ratio(a, b)
