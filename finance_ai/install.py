# -*- coding: utf-8 -*-
"""
FinGuard AI – Install Hooks
Executed once by `bench --site <site> install-app finance_ai`.
"""
import frappe


def after_install():
    """Run after the app is installed on a site."""
    create_default_settings()
    frappe.db.commit()


def create_default_settings():
    """Create the singleton FinGuard Settings document with safe defaults.

    All weights must sum to 100 to ensure the composite risk score is
    properly normalised across the three detection pillars.
    """
    if not frappe.db.exists('FinGuard Settings', 'FinGuard Settings'):
        settings = frappe.new_doc('FinGuard Settings')
        settings.enabled = 1
        settings.scan_mode = 'Hybrid'           # Rule | ML | Hybrid
        settings.anomaly_threshold = 0.75        # Composite score cut-off (0–1)
        settings.lookback_days = 90              # Historical window for model training
        settings.ml_weight = 40                  # % weight – Isolation Forest
        settings.rule_weight = 35               # % weight – Rule engine
        settings.duplicate_weight = 25          # % weight – Duplicate detector
        settings.alert_high_risk_threshold = 0.80   # Score ≥ this → HIGH alert
        settings.alert_medium_risk_threshold = 0.50  # Score ≥ this → MEDIUM alert
        settings.notify_roles = 'Accounts Manager'
        settings.insert(ignore_permissions=True)
        frappe.db.commit()
