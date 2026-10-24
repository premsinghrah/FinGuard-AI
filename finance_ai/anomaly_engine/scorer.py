"""
FinGuard AI — Composite Risk Scorer
=====================================
Combines ML, rule, and duplicate scores into a single weighted risk score
and orchestrates the full scoring pipeline for a single transaction.

No Frappe dependency — pure Python.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np
import pandas as pd

from finance_ai.anomaly_engine.explainer import AnomalyExplainer, format_amount

if TYPE_CHECKING:
    from finance_ai.anomaly_engine.isolation_forest import IsolationForestDetector
    from finance_ai.anomaly_engine.rule_engine import RuleEngine
    from finance_ai.anomaly_engine.duplicate_detector import DuplicateDetector


class AnomalyScorer:
    """
    Calculate and classify composite anomaly risk scores.

    The composite score is a weighted average of three sub-scores:
      - **ML score**        : Isolation Forest anomaly score in [0, 1]
      - **Rule score**      : Proportion of rules triggered in [0, 1]
      - **Duplicate score** : 1.0 if a duplicate is detected, else 0.0

    Parameters
    ----------
    ml_weight:
        Weight (0–100) for the ML model score.
    rule_weight:
        Weight (0–100) for the rule-based score.
    duplicate_weight:
        Weight (0–100) for the duplicate detection score.

    Raises
    ------
    ValueError
        If the three weights do not sum to 100.
    """

    def __init__(
        self,
        ml_weight:        int = 40,
        rule_weight:      int = 35,
        duplicate_weight: int = 25,
    ) -> None:
        total = ml_weight + rule_weight + duplicate_weight
        if total != 100:
            raise ValueError(
                f"Weights must sum to 100, got {total} "
                f"(ml={ml_weight}, rule={rule_weight}, dup={duplicate_weight})."
            )
        self.ml_weight        = ml_weight
        self.rule_weight      = rule_weight
        self.duplicate_weight = duplicate_weight
        self._explainer       = AnomalyExplainer()

    # ------------------------------------------------------------------ #
    # Core scoring
    # ------------------------------------------------------------------ #

    def composite_score(
        self,
        ml_score:        float,
        rule_score:      float,
        duplicate_score: float,
    ) -> float:
        """
        Return the weighted composite risk score in [0, 1].

        Parameters
        ----------
        ml_score:
            Anomaly score from Isolation Forest in [0, 1].
        rule_score:
            Rule-engine score in [0, 1].
        duplicate_score:
            1.0 if a duplicate was detected, else 0.0.

        Returns
        -------
        float in [0, 1]
        """
        score = (
            float(ml_score)        * self.ml_weight
            + float(rule_score)    * self.rule_weight
            + float(duplicate_score) * self.duplicate_weight
        ) / 100.0
        return round(float(np.clip(score, 0.0, 1.0)), 6)

    def classify(
        self,
        score: float,
        high_threshold:   float = 0.75,
        medium_threshold: float = 0.45,
    ) -> str:
        """
        Map a composite score to a risk level label.

        Parameters
        ----------
        score:
            Composite risk score in [0, 1].
        high_threshold:
            Minimum score for 'High Risk'.
        medium_threshold:
            Minimum score for 'Medium Risk'.

        Returns
        -------
        'High Risk', 'Medium Risk', or 'Low Risk'
        """
        if score >= high_threshold:
            return "High Risk"
        if score >= medium_threshold:
            return "Medium Risk"
        return "Low Risk"

    # ------------------------------------------------------------------ #
    # Full single-transaction pipeline
    # ------------------------------------------------------------------ #

    def score_transaction(
        self,
        transaction:      Dict[str, Any],
        feature_df:       pd.DataFrame,
        detector:         "IsolationForestDetector",
        rule_engine:      "RuleEngine",
        dup_detector:     "DuplicateDetector",
        all_transactions: List[Dict[str, Any]],
        high_threshold:   float = 0.75,
        medium_threshold: float = 0.45,
    ) -> Dict[str, Any]:
        """
        Orchestrate full anomaly scoring for a single transaction.

        Parameters
        ----------
        transaction:
            The transaction dict to score.
        feature_df:
            Feature DataFrame row(s) corresponding to this transaction.
            Typically a 1-row slice from the full feature matrix.
        detector:
            Fitted IsolationForestDetector.
        rule_engine:
            Configured RuleEngine instance.
        dup_detector:
            DuplicateDetector instance.
        all_transactions:
            Full list of transactions in the scan window (for dup check).
        high_threshold:
            Score threshold for 'High Risk'.
        medium_threshold:
            Score threshold for 'Medium Risk'.

        Returns
        -------
        dict with keys:
            ml_score, rule_score, duplicate_score, composite_score,
            risk_level, triggered_rules, is_duplicate, duplicate_of,
            duplicate_similarity, summary, reasons, recommendation,
            amount_formatted
        """
        # ── ML score ─────────────────────────────────────────────────────
        try:
            ml_scores = detector.score(feature_df)
            ml_score  = float(ml_scores[0]) if len(ml_scores) else 0.5
        except Exception:
            ml_score = 0.5

        # ── Rule score ───────────────────────────────────────────────────
        triggered_rules = rule_engine.check(transaction)
        rule_score      = rule_engine.rule_score(triggered_rules)

        # ── Duplicate score ──────────────────────────────────────────────
        other_txns    = [t for t in all_transactions if t.get("name") != transaction.get("name")]
        is_dup        = False
        dup_of        = ""
        dup_sim       = 0.0
        dup_reason    = ""

        for other in other_txns:
            _is_dup, _sim, _reason = dup_detector.is_duplicate(transaction, other)
            if _is_dup:
                is_dup     = True
                dup_of     = other.get("name", "")
                dup_sim    = _sim
                dup_reason = _reason
                break

        duplicate_score = 1.0 if is_dup else 0.0

        # ── Composite ────────────────────────────────────────────────────
        c_score    = self.composite_score(ml_score, rule_score, duplicate_score)
        risk_level = self.classify(c_score, high_threshold, medium_threshold)

        # ── Explanation ──────────────────────────────────────────────────
        explanation = self._explainer.explain(
            transaction    = transaction,
            composite_score= c_score,
            triggered_rules= triggered_rules,
            is_duplicate   = is_dup,
            duplicate_reason = dup_reason,
        )

        return {
            "ml_score":           round(ml_score, 6),
            "rule_score":         round(rule_score, 6),
            "duplicate_score":    duplicate_score,
            "composite_score":    c_score,
            "risk_level":         risk_level,
            "triggered_rules":    triggered_rules,
            "is_duplicate":       is_dup,
            "duplicate_of":       dup_of,
            "duplicate_similarity": round(dup_sim, 2),
            "summary":            explanation["summary"],
            "reasons":            explanation["reasons"],
            "recommendation":     explanation["recommendation"],
            "amount_formatted":   format_amount(float(transaction.get("amount", 0) or 0)),
        }
