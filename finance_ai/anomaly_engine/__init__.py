"""
FinGuard AI — Anomaly Engine
============================
ML-powered financial anomaly detection pipeline.

Components
----------
features          : Feature engineering from GL / Journal Entry records
isolation_forest  : Isolation Forest model wrapper (train + score)
rule_engine       : Deterministic rule-based checks
duplicate_detector: Fuzzy duplicate invoice / payment detection
explainer         : Human-readable risk explanations
scorer            : Composite risk score calculator
scanner           : Frappe integration layer (event hooks + scheduled tasks)
"""

from finance_ai.anomaly_engine.scorer import AnomalyScorer  # noqa: F401

__all__ = ["AnomalyScorer"]
