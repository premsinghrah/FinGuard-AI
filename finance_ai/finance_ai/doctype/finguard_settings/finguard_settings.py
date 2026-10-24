# Copyright (c) 2024, FinGuard AI
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


class FinGuardSettings(Document):
    """
    Singleton settings document for FinGuard AI.
    Configures weights, thresholds, notifications, and model parameters.
    """

    def validate(self):
        """Validate that scoring weights sum to exactly 100."""
        ml    = int(self.ml_weight or 0)
        rule  = int(self.rule_weight or 0)
        dup   = int(self.duplicate_weight or 0)
        total = ml + rule + dup
        if total != 100:
            frappe.throw(
                _(
                    "Scoring weights must sum to 100. "
                    "Current total: ML ({0}) + Rule ({1}) + Duplicate ({2}) = {3}."
                ).format(ml, rule, dup, total)
            )

        if self.high_risk_threshold <= self.medium_risk_threshold:
            frappe.throw(
                _("High Risk Threshold ({0}) must be greater than Medium Risk Threshold ({1}).").format(
                    self.high_risk_threshold, self.medium_risk_threshold
                )
            )

    @staticmethod
    def get_settings() -> dict:
        """
        Return all settings as a plain dict with safe defaults.

        Can be called as ``FinGuardSettings.get_settings()`` from any module
        that imports the controller.
        """
        defaults = {
            "enabled":                        True,
            "scan_mode":                      "Hybrid",
            "ml_weight":                      40,
            "rule_weight":                    35,
            "duplicate_weight":               25,
            "anomaly_threshold":              0.05,
            "high_risk_threshold":            0.80,
            "medium_risk_threshold":          0.50,
            "large_amount_threshold":         500_000,
            "lookback_days":                  90,
            "duplicate_similarity_threshold": 85,
            "duplicate_date_window":          3,
            "notify_on_high_risk":            True,
            "email_digest":                   False,
            "model_path":                     "",
            "auto_retrain":                   True,
            "retrain_frequency":              "Weekly",
        }
        try:
            doc = frappe.get_single("FinGuard Settings")
            return {
                "enabled":                        bool(doc.enabled),
                "scan_mode":                      doc.scan_mode or "Hybrid",
                "ml_weight":                      int(doc.ml_weight or 40),
                "rule_weight":                    int(doc.rule_weight or 35),
                "duplicate_weight":               int(doc.duplicate_weight or 25),
                "anomaly_threshold":              float(doc.anomaly_threshold or 0.05),
                "high_risk_threshold":            float(doc.high_risk_threshold or 0.80),
                "medium_risk_threshold":          float(doc.medium_risk_threshold or 0.50),
                "large_amount_threshold":         float(doc.large_amount_threshold or 500_000),
                "lookback_days":                  int(doc.lookback_days or 90),
                "duplicate_similarity_threshold": int(doc.duplicate_similarity_threshold or 85),
                "duplicate_date_window":          int(doc.duplicate_date_window or 3),
                "notify_on_high_risk":            bool(doc.notify_on_high_risk),
                "email_digest":                   bool(doc.email_digest),
                "model_path":                     doc.model_path or "",
                "auto_retrain":                   bool(doc.auto_retrain),
                "retrain_frequency":              doc.retrain_frequency or "Weekly",
            }
        except Exception:
            return defaults
