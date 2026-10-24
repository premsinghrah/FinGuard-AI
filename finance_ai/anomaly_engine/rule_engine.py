"""
FinGuard AI — Rule Engine
==========================
Deterministic, auditable rule-based checks for financial transactions.

Each rule targets a specific anomaly pattern drawn from financial audit
literature and internal control frameworks.  Rules are fast and produce
human-readable trigger codes that feed directly into the explainer.

No Frappe dependency — pure Python.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

#: All rule codes emitted by this engine.
RULE_CODES: List[str] = [
    "ROUND_AMOUNT",
    "LARGE_AMOUNT",
    "OFF_HOURS_POSTING",
    "WEEKEND_POSTING",
    "ZERO_AMOUNT",
    "NEGATIVE_AMOUNT",
    "HIGH_VELOCITY_3D",
    "SELF_TRANSFER",
    "MISSING_NARRATION",
    "UNUSUAL_ACCOUNT_COMBINATION",
]

#: Default rule weights (relative risk severity, used by rule_score()).
_DEFAULT_RULE_WEIGHTS: Dict[str, float] = {
    "ROUND_AMOUNT":                  0.55,
    "LARGE_AMOUNT":                  0.70,
    "OFF_HOURS_POSTING":             0.60,
    "WEEKEND_POSTING":               0.45,
    "ZERO_AMOUNT":                   0.80,
    "NEGATIVE_AMOUNT":               0.75,
    "HIGH_VELOCITY_3D":              0.65,
    "SELF_TRANSFER":                 0.90,
    "MISSING_NARRATION":             0.40,
    "UNUSUAL_ACCOUNT_COMBINATION":   0.60,
}

#: Human-readable descriptions of each rule (used by explainer).
RULE_DESCRIPTIONS: Dict[str, str] = {
    "ROUND_AMOUNT":                "Amount is an exact round number (divisible by 1,000)",
    "LARGE_AMOUNT":                "Amount exceeds the large-transaction threshold",
    "OFF_HOURS_POSTING":           "Transaction posted outside business hours (before 08:00 or after 20:00)",
    "WEEKEND_POSTING":             "Transaction posted on a Saturday or Sunday",
    "ZERO_AMOUNT":                 "Transaction amount is zero",
    "NEGATIVE_AMOUNT":             "Transaction amount is negative (unusual for this entry type)",
    "HIGH_VELOCITY_3D":            "More than 5 transactions from the same party within 3 days",
    "SELF_TRANSFER":               "Debit and credit parties appear to be the same entity",
    "MISSING_NARRATION":           "No narration or description was provided",
    "UNUSUAL_ACCOUNT_COMBINATION": "Debit and credit accounts belong to the same account type",
}


class RuleEngine:
    """
    Evaluate a set of deterministic anomaly rules against transactions.

    Parameters
    ----------
    config:
        Optional dict to override default rule thresholds.  Keys:
          - ``large_amount_threshold``  (float, default 500_000)
          - ``off_hours_start``         (int hour, default 20)
          - ``off_hours_end``           (int hour, default 8)
          - ``high_velocity_count``     (int, default 5)
          - ``round_divisor``           (int, default 1_000)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.large_amount_threshold = float(cfg.get("large_amount_threshold", 500_000))
        self.off_hours_start        = int(cfg.get("off_hours_start", 20))   # evening
        self.off_hours_end          = int(cfg.get("off_hours_end", 8))      # morning
        self.high_velocity_count    = int(cfg.get("high_velocity_count", 5))
        self.round_divisor          = int(cfg.get("round_divisor", 1_000))
        self._weights               = dict(_DEFAULT_RULE_WEIGHTS)
        self._weights.update(cfg.get("rule_weights", {}))

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def check(self, transaction: Dict[str, Any]) -> List[str]:
        """
        Evaluate all rules against a single transaction dict.

        Parameters
        ----------
        transaction:
            Dict with fields: amount, posting_hour, posting_day_of_week,
            party, debit_party, credit_party, account_type,
            debit_account_type, credit_account_type, narration,
            velocity_3d.

        Returns
        -------
        list[str]
            List of triggered rule codes (may be empty).
        """
        triggered: List[str] = []

        if self._check_zero_amount(transaction):
            triggered.append("ZERO_AMOUNT")
        if self._check_negative_amount(transaction):
            triggered.append("NEGATIVE_AMOUNT")
        if self._check_round_amount(transaction):
            triggered.append("ROUND_AMOUNT")
        if self._check_large_amount(transaction):
            triggered.append("LARGE_AMOUNT")
        if self._check_off_hours(transaction):
            triggered.append("OFF_HOURS_POSTING")
        if self._check_weekend(transaction):
            triggered.append("WEEKEND_POSTING")
        if self._check_high_velocity(transaction):
            triggered.append("HIGH_VELOCITY_3D")
        if self._check_self_transfer(transaction):
            triggered.append("SELF_TRANSFER")
        if self._check_missing_narration(transaction):
            triggered.append("MISSING_NARRATION")
        if self._check_unusual_account_combination(transaction):
            triggered.append("UNUSUAL_ACCOUNT_COMBINATION")

        return triggered

    def check_batch(self, transactions: List[Dict[str, Any]]) -> List[List[str]]:
        """
        Evaluate all rules for a list of transactions.

        Parameters
        ----------
        transactions:
            List of transaction dicts.

        Returns
        -------
        list[list[str]]
            Parallel list of triggered rule codes per transaction.
        """
        return [self.check(t) for t in transactions]

    def rule_score(self, triggered_rules: List[str]) -> float:
        """
        Convert a list of triggered rule codes into a [0, 1] risk score.

        Uses a weighted OR approach — the score is bounded below by the
        maximum individual weight and boosted by co-occurring rules.

        Parameters
        ----------
        triggered_rules:
            List of rule codes returned by check().

        Returns
        -------
        float
            Risk score in [0, 1].  0.0 = no rules triggered.
        """
        if not triggered_rules:
            return 0.0

        weights = [self._weights.get(r, 0.5) for r in triggered_rules]
        # Start at max single-rule weight, then diminishing additions
        score = max(weights)
        for w in sorted(weights, reverse=True)[1:]:
            score = score + (1 - score) * w * 0.4   # asymptotic approach to 1
        return round(min(score, 1.0), 6)

    # ------------------------------------------------------------------ #
    # Private rule implementations
    # ------------------------------------------------------------------ #

    def _get_amount(self, t: Dict[str, Any]) -> float:
        return float(t.get("amount", 0) or 0)

    def _get_hour(self, t: Dict[str, Any]) -> int:
        return int(t.get("posting_hour", 12) or 12)

    def _get_dow(self, t: Dict[str, Any]) -> int:
        """Day of week: 0 = Monday … 6 = Sunday."""
        return int(t.get("posting_day_of_week", 0) or 0)

    def _check_zero_amount(self, t: Dict[str, Any]) -> bool:
        """Amount is exactly 0."""
        return self._get_amount(t) == 0.0

    def _check_negative_amount(self, t: Dict[str, Any]) -> bool:
        """Amount is negative (unusual for most entry types)."""
        return self._get_amount(t) < 0.0

    def _check_round_amount(self, t: Dict[str, Any]) -> bool:
        """Amount is divisible by round_divisor (default 1,000)."""
        amount = self._get_amount(t)
        if amount <= 0:
            return False
        return (amount % self.round_divisor) == 0

    def _check_large_amount(self, t: Dict[str, Any]) -> bool:
        """Amount exceeds the configurable large-amount threshold."""
        return self._get_amount(t) > self.large_amount_threshold

    def _check_off_hours(self, t: Dict[str, Any]) -> bool:
        """Transaction posted before off_hours_end or after off_hours_start."""
        hour = self._get_hour(t)
        return hour < self.off_hours_end or hour >= self.off_hours_start

    def _check_weekend(self, t: Dict[str, Any]) -> bool:
        """Transaction posted on Saturday (5) or Sunday (6)."""
        return self._get_dow(t) >= 5

    def _check_high_velocity(self, t: Dict[str, Any]) -> bool:
        """More than high_velocity_count transactions from same party in 3 days."""
        v3d = int(t.get("velocity_3d", 0) or 0)
        return v3d > self.high_velocity_count

    def _check_self_transfer(self, t: Dict[str, Any]) -> bool:
        """Debit and credit party/account appear to be the same."""
        debit_party  = str(t.get("debit_party", "") or "").strip().lower()
        credit_party = str(t.get("credit_party", "") or "").strip().lower()
        if debit_party and credit_party and debit_party == credit_party:
            return True
        # Also check if narration mentions 'self' or 'own account'
        narration = str(t.get("narration", "") or "").lower()
        return bool(re.search(r"\bself\b|\bown account\b", narration))

    def _check_missing_narration(self, t: Dict[str, Any]) -> bool:
        """Narration / description is empty or too short (< 5 chars)."""
        narration = str(t.get("narration", "") or "").strip()
        return len(narration) < 5

    def _check_unusual_account_combination(self, t: Dict[str, Any]) -> bool:
        """Debit and credit accounts belong to the same account type."""
        debit_type  = str(t.get("debit_account_type", "") or "").strip().lower()
        credit_type = str(t.get("credit_account_type", "") or "").strip().lower()
        if not debit_type or not credit_type:
            return False
        return debit_type == credit_type
