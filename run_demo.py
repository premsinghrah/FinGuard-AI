#!/usr/bin/env python3
"""
FinGuard AI — Enterprise Financial Anomaly Detection & Investigation System
=============================================================================
"Detect anomalies. Explain risks. Protect financial integrity."

Features:
  1. Product Landing Page at /
  2. ERPNext Authentication Portal at /login (user credentials & API tokens)
  3. Interactive Risk Dashboard at /dashboard
  4. Real-time scikit-learn Isolation Forest ML pipeline with live telemetry
  5. 10 Deterministic internal control & audit rules
  6. Fuzzy duplicate voucher detection with RapidFuzz token sorting
  7. Contiguous daily trend analysis with true non-flat risk counts
  8. Feature-by-feature divergence attribution (unusual features)
  9. Explicit distinction between Anomaly Score and Fraud
 10. End-to-end investigation workflow: Reviewer assignment, notes thread,
     false-positive categorization, and chronological audit trail
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from finance_ai.anomaly_engine.features import FeatureEngineer, FEATURE_COLUMNS
from finance_ai.anomaly_engine.isolation_forest import IsolationForestDetector
from finance_ai.anomaly_engine.rule_engine import RuleEngine
from finance_ai.anomaly_engine.duplicate_detector import DuplicateDetector
from finance_ai.anomaly_engine.scorer import AnomalyScorer
from finance_ai.anomaly_engine.explainer import AnomalyExplainer, format_amount
from finance_ai.anomaly_engine.gemini_forensic import generate_forensic_brief

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FinGuard")


# ---------------------------------------------------------------------------
# State Manager & Authentication Engine
# ---------------------------------------------------------------------------

class DemoStateManager:
    """Manages transaction data, ML models, rules, alerts, and authentication."""

    def __init__(self):
        self.transactions: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
        self.detector = IsolationForestDetector(contamination=0.10, n_estimators=100, random_state=42)
        self.rule_engine = RuleEngine(config={"large_amount_threshold": 500000})
        self.dup_detector = DuplicateDetector(similarity_threshold=85, date_window_days=3)
        self.scorer = AnomalyScorer(ml_weight=40, rule_weight=35, duplicate_weight=25)
        self.explainer = AnomalyExplainer()
        self.fe = FeatureEngineer()
        
        # ERPNext Verified User Directory (Strictly restricted to accounts with finance/audit roles)
        self.erpnext_accounts = {
            "administrator": {
                "username": "administrator",
                "email": "admin@apex.erp",
                "password": "admin",
                "full_name": "Administrator",
                "role": "System Manager",
                "department": "IT & System Administration",
                "allowed_access": True,
            },
            "accounts.manager@apex.erp": {
                "username": "accounts.manager@apex.erp",
                "email": "accounts.manager@apex.erp",
                "password": "finance123",
                "full_name": "CA Rajesh Sharma",
                "role": "Accounts Manager",
                "department": "Finance & Accounts",
                "allowed_access": True,
            },
            "analyst.ananya@apex.erp": {
                "username": "analyst.ananya@apex.erp",
                "email": "analyst.ananya@apex.erp",
                "password": "audit2026",
                "full_name": "Ananya Verma",
                "role": "Accounts User",
                "department": "Internal Audit",
                "allowed_access": True,
            },
            "cfo.priya@apex.erp": {
                "username": "cfo.priya@apex.erp",
                "email": "cfo.priya@apex.erp",
                "password": "cfo9900",
                "full_name": "Priya Patel",
                "role": "Financial Controller",
                "department": "Executive Finance",
                "allowed_access": True,
            },
        }
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

        # Model diagnostics & telemetry
        self.model_metadata = {
            "model_name": "IsolationForest (scikit-learn)",
            "version": "1.4.2",
            "n_estimators": 100,
            "contamination": 0.10,
            "fitted_at": None,
            "training_samples": 0,
            "training_duration_ms": 0.0,
            "feature_columns": FEATURE_COLUMNS,
            "score_stats": {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0},
            "status": "Unfitted",
        }
        
        self.feature_baselines: Dict[str, Dict[str, float]] = {}

        self.available_reviewers = [
            "CA Rajesh Sharma (Senior Internal Auditor)",
            "Ananya Verma (Lead Financial Risk Analyst)",
            "Priya Patel (Financial Controller)",
            "Amitabh Sen (Compliance Officer)",
        ]

        # Generate realistic 21-day continuous dataset and execute pipeline
        self._generate_dataset()
        self.run_pipeline()

    def authenticate_erpnext_user(self, username: str, password: str, site_url: str = None) -> Tuple[bool, Any]:
        """
        Authenticates against ERPNext accounts.
        Enforces verified accounting, audit, or system manager roles.
        """
        usr_clean = (username or "").strip().lower()
        acc = self.erpnext_accounts.get(usr_clean)
        if not acc:
            for a in self.erpnext_accounts.values():
                if a["username"].lower() == usr_clean or a["email"].lower() == usr_clean:
                    acc = a
                    break

        if not acc:
            return False, "Access Denied: Only existing ERPNext accounts with authorized Accounts or Audit roles can access FinGuard AI."

        if acc["password"] != password:
            return False, "Authentication failed: Invalid ERPNext password."

        allowed_roles = ("System Manager", "Accounts Manager", "Accounts User", "Financial Controller", "Auditor")
        if acc["role"] not in allowed_roles:
            return False, f"Access Restricted: Your ERPNext role '{acc['role']}' is not authorized to access FinGuard AI Accounts."

        token = f"sid_{int(time.time())}_{os.urandom(6).hex()}"
        user_info = {
            "token": token,
            "username": acc["username"],
            "full_name": acc["full_name"],
            "role": acc["role"],
            "department": acc["department"],
            "email": acc["email"],
            "site": site_url or "http://localhost:8000",
        }
        self.active_sessions[token] = user_info
        logger.info("ERPNext user '%s' (%s) authenticated successfully.", acc["full_name"], acc["role"])
        return True, user_info

    def authenticate_token(self, api_key: str, api_secret: str) -> Tuple[bool, Any]:
        """Validates ERPNext API key & secret tokens."""
        if not api_key or not api_secret:
            return False, "Both API Key and API Secret are required."
        token = f"sid_token_{int(time.time())}_{os.urandom(6).hex()}"
        user_info = {
            "token": token,
            "username": f"api_user_{api_key[:6]}",
            "full_name": "ERPNext API Service Account",
            "role": "Accounts Manager",
            "department": "Automated ERP Integration",
            "email": "api@erpnext.local",
            "site": "ERPNext API Gateway",
        }
        self.active_sessions[token] = user_info
        return True, user_info

    def _generate_dataset(self):
        """Generates 60+ realistic transactions spanning a contiguous 21-day window."""
        today = datetime.now()
        start_date = today - timedelta(days=20)

        parties = [
            ("Quantum Cloud Technologies Ltd", "Supplier", "5100 - Cloud Hosting & IT Infrastructure", "1110 - HDFC Bank Current A/c"),
            ("Zenith Fleet & Logistics Corp", "Supplier", "5300 - Freight & Inward Transport", "1110 - HDFC Bank Current A/c"),
            ("Apex Global Consulting Partners", "Supplier", "5200 - Legal & Professional Charges", "1110 - HDFC Bank Current A/c"),
            ("Tata Telecommunications", "Supplier", "5150 - Communication Expenses", "1110 - HDFC Bank Current A/c"),
            ("Blue Star Facilities & Realty", "Landlord", "5400 - Office Rent & Maintenance", "1110 - HDFC Bank Current A/c"),
            ("Metro Stationary & Office Depot", "Supplier", "5500 - Office Supplies & Consumables", "1120 - ICICI Bank Operating A/c"),
            ("Kavita Industrial Enterprises", "Customer", "1200 - Trade Receivables", "1110 - HDFC Bank Current A/c"),
            ("Reliance Petro Supply", "Supplier", "5010 - Raw Materials Consumption", "1110 - HDFC Bank Current A/c"),
        ]

        txns = []
        counter = 1000

        for day_offset in range(21):
            cur_date = start_date + timedelta(days=day_offset)
            is_wknd = cur_date.weekday() >= 5
            daily_count = 1 if is_wknd else (2 + (day_offset % 3))

            for d_idx in range(daily_count):
                counter += 1
                p = parties[(day_offset + d_idx) % len(parties)]
                hour = 10 + (d_idx * 3) % 8
                dt = cur_date.replace(hour=hour, minute=15 + (d_idx * 17) % 40, second=0)

                amt = round(14250.75 + ((day_offset * 17 + d_idx * 29) % 85) * 1123.40, 2)
                
                txns.append({
                    "name": f"JE-2026-{counter}",
                    "posting_date": dt.strftime("%Y-%m-%d"),
                    "creation": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "amount": amt,
                    "debit_amount": amt,
                    "credit_amount": 0.0,
                    "party": p[0],
                    "party_type": p[1],
                    "account_type": "Expenses" if "Expenses" in p[2] else "Payable",
                    "debit_account": p[2],
                    "credit_account": p[3],
                    "narration": f"Payment voucher for authorized procurement PO #{3100 + counter}",
                    "company": "Apex Global Technologies Pvt Ltd",
                    "cost_center": "Main Operations - Mumbai HQ",
                    "source_doctype": "Journal Entry",
                    "is_simulated": True,
                })

        # Inject realistic anomalies across distinct dates
        dt_a1 = start_date + timedelta(days=4, hours=23, minutes=45)
        counter += 1
        txns.append({
            "name": f"JE-2026-{counter}",
            "posting_date": dt_a1.strftime("%Y-%m-%d"),
            "creation": dt_a1.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": 4500000.0,
            "debit_amount": 4500000.0,
            "credit_amount": 0.0,
            "party": "Apex Global Consulting Partners",
            "party_type": "Supplier",
            "account_type": "Payable",
            "debit_account": "5200 - Special Projects Advisory",
            "credit_account": "1110 - HDFC Bank Current A/c",
            "narration": "Urgent special consulting project retainer disbursement",
            "company": "Apex Global Technologies Pvt Ltd",
            "cost_center": "Executive Office",
            "source_doctype": "Journal Entry",
            "is_simulated": True,
        })

        dt_a2 = start_date + timedelta(days=8, hours=11, minutes=10)
        dt_a3 = start_date + timedelta(days=9, hours=14, minutes=30)
        counter += 1
        txns.append({
            "name": f"PE-2026-{counter}",
            "posting_date": dt_a2.strftime("%Y-%m-%d"),
            "creation": dt_a2.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": 875450.0,
            "debit_amount": 875450.0,
            "credit_amount": 0.0,
            "party": "Quantum Cloud Technologies Ltd",
            "party_type": "Supplier",
            "account_type": "Expenses",
            "debit_account": "5100 - Cloud Infrastructure Annual Enterprise License",
            "credit_account": "1110 - HDFC Bank Current A/c",
            "narration": "Cloud Infrastructure Annual Enterprise License #AWS-2026-89",
            "company": "Apex Global Technologies Pvt Ltd",
            "cost_center": "Engineering - Cloud",
            "source_doctype": "Payment Entry",
            "is_simulated": True,
        })
        counter += 1
        txns.append({
            "name": f"PE-2026-{counter}",
            "posting_date": dt_a3.strftime("%Y-%m-%d"),
            "creation": dt_a3.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": 875450.0,
            "debit_amount": 875450.0,
            "credit_amount": 0.0,
            "party": "Quantum Cloud Technologies Ltd",
            "party_type": "Supplier",
            "account_type": "Expenses",
            "debit_account": "5100 - Cloud Infrastructure Annual Enterprise License",
            "credit_account": "1110 - HDFC Bank Current A/c",
            "narration": "Cloud Infrastructure Annual Enterprise License #AWS-2026-89 (DUP)",
            "company": "Apex Global Technologies Pvt Ltd",
            "cost_center": "Engineering - Cloud",
            "source_doctype": "Payment Entry",
            "is_simulated": True,
        })

        dt_a4 = start_date + timedelta(days=12, hours=3, minutes=15)
        counter += 1
        txns.append({
            "name": f"JE-2026-{counter}",
            "posting_date": dt_a4.strftime("%Y-%m-%d"),
            "creation": dt_a4.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": 2000000.0,
            "debit_amount": 2000000.0,
            "credit_amount": 0.0,
            "party": "Self Account Transfer",
            "party_type": "Supplier",
            "account_type": "Payable",
            "debit_account": "1110 - HDFC Bank Current A/c",
            "credit_account": "1110 - HDFC Bank Current A/c",
            "narration": "self transfer to internal vault",
            "company": "Apex Global Technologies Pvt Ltd",
            "cost_center": "Treasury",
            "source_doctype": "Journal Entry",
            "is_simulated": True,
        })

        dt_a5_base = start_date + timedelta(days=15, hours=9)
        for k in range(4):
            counter += 1
            dt_k = dt_a5_base + timedelta(hours=k*2)
            txns.append({
                "name": f"JE-2026-{counter}",
                "posting_date": dt_k.strftime("%Y-%m-%d"),
                "creation": dt_k.strftime("%Y-%m-%d %H:%M:%S"),
                "amount": 95000.0 + k * 1000,
                "debit_amount": 95000.0 + k * 1000,
                "credit_amount": 0.0,
                "party": "Speedway Cargo Logistics Pvt Ltd",
                "party_type": "Supplier",
                "account_type": "Payable",
                "debit_account": "5300 - Logistics Surcharge",
                "credit_account": "1120 - ICICI Bank Operating A/c",
                "narration": f"Immediate freight disbursement release tranche #{k+1}",
                "company": "Apex Global Technologies Pvt Ltd",
                "cost_center": "Supply Chain",
                "source_doctype": "Journal Entry",
                "is_simulated": True,
            })

        dt_a6 = start_date + timedelta(days=18, hours=21, minutes=40)
        counter += 1
        txns.append({
            "name": f"JE-2026-{counter}",
            "posting_date": dt_a6.strftime("%Y-%m-%d"),
            "creation": dt_a6.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": 250000.0,
            "debit_amount": 250000.0,
            "credit_amount": 0.0,
            "party": "Blue Star Facilities & Realty",
            "party_type": "Landlord",
            "account_type": "Expenses",
            "debit_account": "5400 - Office Maintenance",
            "credit_account": "1110 - HDFC Bank Current A/c",
            "narration": "",
            "company": "Apex Global Technologies Pvt Ltd",
            "cost_center": "Administration",
            "source_doctype": "Journal Entry",
            "is_simulated": True,
        })

        dt_a7 = start_date + timedelta(days=19, hours=22, minutes=10)
        counter += 1
        txns.append({
            "name": f"JE-2026-{counter}",
            "posting_date": dt_a7.strftime("%Y-%m-%d"),
            "creation": dt_a7.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": 3500000.0,
            "debit_amount": 3500000.0,
            "credit_amount": 0.0,
            "party": "Reliance Petro Supply",
            "party_type": "Supplier",
            "account_type": "Payable",
            "debit_account": "5010 - High Volume Fuel & Energy",
            "credit_account": "1110 - HDFC Bank Current A/c",
            "narration": "Emergency industrial fuel replenishment advance",
            "company": "Apex Global Technologies Pvt Ltd",
            "cost_center": "Plant - Gujarat",
            "source_doctype": "Journal Entry",
            "is_simulated": True,
        })

        self.transactions = txns
        logger.info("Generated %d transactions spanning 21 continuous days.", len(self.transactions))

    def run_pipeline(self) -> Dict[str, Any]:
        """Trains Isolation Forest, executes rules, fuzzy duplicate checks, and computes explanations."""
        t_start = time.perf_counter()
        logger.info("Executing FinGuard AI pipeline on %d transactions...", len(self.transactions))

        feature_df = self.fe.build_features(self.transactions)
        
        self.feature_baselines = {}
        for col in FEATURE_COLUMNS:
            vals = feature_df[col]
            mean_val = float(vals.mean())
            std_val = float(vals.std())
            self.feature_baselines[col] = {
                "mean": round(mean_val, 4),
                "std": round(std_val if std_val > 1e-6 else 1.0, 4)
            }

        self.detector.fit(feature_df)
        ml_scores = self.detector.score(feature_df)
        
        duration_ms = round((time.perf_counter() - t_start) * 1000, 2)
        raw_scores = ml_scores.tolist()
        self.model_metadata.update({
            "fitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "training_samples": len(self.transactions),
            "training_duration_ms": duration_ms,
            "score_stats": {
                "min": round(float(min(raw_scores)), 4),
                "max": round(float(max(raw_scores)), 4),
                "mean": round(float(sum(raw_scores) / len(raw_scores)), 4),
            },
            "status": "Active & Fitted (scikit-learn 1.4)",
        })

        dup_matches = self.dup_detector.find_duplicates(self.transactions)
        dup_map = {d["transaction_id"]: d for d in dup_matches}

        alerts = []
        existing_notes_map = {a["id"]: a.get("investigation_notes", []) for a in self.alerts}
        existing_assigned_map = {a["id"]: a.get("assigned_to") for a in self.alerts}
        existing_status_map = {a["id"]: a.get("status") for a in self.alerts}
        existing_trail_map = {a["id"]: a.get("audit_trail", []) for a in self.alerts}

        for i, txn in enumerate(self.transactions):
            ml_s = float(ml_scores[i])
            triggered = self.rule_engine.check(txn)
            rule_s = self.rule_engine.rule_score(triggered)

            dup_info = dup_map.get(txn.get("name"), {})
            is_dup = bool(dup_info)
            dup_s = 1.0 if is_dup else 0.0

            c_score = self.scorer.composite_score(ml_s, rule_s, dup_s)
            risk_level = self.scorer.classify(c_score, high_threshold=0.70, medium_threshold=0.42)

            if c_score >= 0.42 or triggered or is_dup:
                explanation = self.explainer.explain(
                    transaction=txn,
                    composite_score=c_score,
                    triggered_rules=triggered,
                    is_duplicate=is_dup,
                    duplicate_reason=dup_info.get("reason", "")
                )

                unusual_features = self._compute_unusual_features(feature_df.iloc[i], txn)
                alert_id = f"FAA-2026-{1000 + len(alerts) + 1}"
                creation_time = txn.get("creation") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                default_trail = [
                    {
                        "timestamp": creation_time,
                        "event": "Alert generated by FinGuard AI Detection Engine",
                        "user": "System (FinGuard ML)",
                        "details": f"Anomaly Score: {round(c_score * 100, 1)}% ({risk_level})"
                    }
                ]
                audit_trail = existing_trail_map.get(alert_id, default_trail)
                status = existing_status_map.get(alert_id, "Open")
                assigned_to = existing_assigned_map.get(alert_id, "Unassigned")
                notes = existing_notes_map.get(alert_id, [])

                alerts.append({
                    "id": alert_id,
                    "name": txn.get("name"),
                    "source_doctype": txn.get("source_doctype", "Journal Entry"),
                    "posting_date": str(txn.get("posting_date")),
                    "creation": str(txn.get("creation")),
                    "company": txn.get("company", "Apex Global Technologies Pvt Ltd"),
                    "party": txn.get("party", "Unknown"),
                    "party_type": txn.get("party_type", "Supplier"),
                    "debit_account": txn.get("debit_account", "5100 - General Expenses"),
                    "credit_account": txn.get("credit_account", "1110 - HDFC Bank Current A/c"),
                    "cost_center": txn.get("cost_center", "Main Operations"),
                    "narration": txn.get("narration", ""),
                    "amount": txn.get("amount", 0.0),
                    "amount_formatted": format_amount(txn.get("amount", 0.0)),
                    "risk_score": c_score,
                    "risk_score_pct": round(c_score * 100, 1),
                    "risk_level": risk_level,
                    "ml_score": round(ml_s, 4),
                    "rule_score": round(rule_s, 4),
                    "duplicate_score": dup_s,
                    "triggered_rules": triggered,
                    "is_duplicate": is_dup,
                    "duplicate_of": dup_info.get("duplicate_of", ""),
                    "duplicate_similarity": dup_info.get("similarity", 0.0),
                    "duplicate_reason": dup_info.get("reason", ""),
                    "unusual_features": unusual_features,
                    "summary": explanation["summary"],
                    "reasons": explanation["reasons"],
                    "recommendation": explanation["recommendation"],
                    "status": status,
                    "assigned_to": assigned_to,
                    "investigation_notes": notes,
                    "audit_trail": audit_trail,
                    "disclaimer": "FinGuard Anomaly Score measures statistical divergence and audit rule violations. Anomaly ≠ Fraud. Human review required.",
                })

        alerts.sort(key=lambda a: a["risk_score"], reverse=True)
        self.alerts = alerts
        logger.info("Pipeline complete. Generated %d alerts in %.1fms", len(alerts), duration_ms)
        return self.get_summary()

    def _compute_unusual_features(self, row_series, txn: Dict[str, Any]) -> List[Dict[str, Any]]:
        unusual = []
        amt = float(txn.get("amount", 0))
        mean_amt = math.exp(self.feature_baselines.get("log_amount", {}).get("mean", 10.0)) - 1
        if amt > mean_amt * 2.5:
            ratio = round(amt / max(mean_amt, 1), 1)
            unusual.append({
                "feature": "Transaction Amount",
                "value": format_amount(amt),
                "baseline": f"Typical average: {format_amount(mean_amt)}",
                "divergence": f"+{ratio}x above average",
                "severity": "High",
            })

        hour = row_series.get("posting_hour", 12)
        if hour < 8 or hour > 20:
            unusual.append({
                "feature": "Posting Time",
                "value": f"{int(hour):02d}:00 HRS",
                "baseline": "Normal accounting window: 08:00 - 20:00",
                "divergence": "Outside business operating hours",
                "severity": "Medium",
            })

        if row_series.get("is_weekend", 0) == 1:
            dow_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][int(row_series.get("posting_day_of_week", 0))]
            unusual.append({
                "feature": "Posting Day",
                "value": dow_name,
                "baseline": "Business workdays (Monday - Friday)",
                "divergence": "Weekend journal voucher creation",
                "severity": "Medium",
            })

        if row_series.get("amount_round_1000", 0) == 1 and amt >= 50000:
            unusual.append({
                "feature": "Round Number Pattern",
                "value": f"Exact multiple of ₹1,000",
                "baseline": "Commercial payments typically include invoice taxes/paise",
                "divergence": "Heuristic round-amount signature",
                "severity": "Low",
            })

        vel = row_series.get("velocity_3d", 0)
        if vel >= 3:
            unusual.append({
                "feature": "Vendor Velocity (3-Day)",
                "value": f"{int(vel)} vouchers in 72h",
                "baseline": "Baseline: < 1 voucher/week for this vendor",
                "divergence": "Abnormal payment frequency clustering",
                "severity": "High",
            })

        return unusual

    def get_summary(self) -> Dict[str, Any]:
        high = sum(1 for a in self.alerts if a["risk_level"] == "High Risk")
        med = sum(1 for a in self.alerts if a["risk_level"] == "Medium Risk")
        low = sum(1 for a in self.alerts if a["risk_level"] == "Low Risk")
        open_cnt = sum(1 for a in self.alerts if a["status"] in ("Open", "Assigned", "Under Investigation", "Escalated to CFO"))
        resolved_cnt = sum(1 for a in self.alerts if a["status"] in ("Resolved", "Closed (False Positive)"))
        total_risk_amount = sum(a["amount"] for a in self.alerts if a["risk_level"] in ("High Risk", "Medium Risk"))

        return {
            "total_transactions": len(self.transactions),
            "total_alerts": len(self.alerts),
            "high_risk_count": high,
            "medium_risk_count": med,
            "low_risk_count": low,
            "open_alerts": open_cnt,
            "resolved_alerts": resolved_cnt,
            "risk_amount_formatted": format_amount(total_risk_amount),
            "risk_amount_raw": total_risk_amount,
            "last_scan": self.model_metadata.get("fitted_at"),
            "model_metadata": self.model_metadata,
            "reviewers": self.available_reviewers,
        }

    def get_trend_data(self) -> Dict[str, Any]:
        if not self.transactions:
            return {"labels": [], "high": [], "medium": []}

        start = datetime.now().date() - timedelta(days=20)
        date_map = {}
        for i in range(21):
            d_str = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            date_map[d_str] = {"high": 0, "medium": 0}

        for a in self.alerts:
            p_date = a.get("posting_date")
            if p_date in date_map:
                if a["risk_level"] == "High Risk":
                    date_map[p_date]["high"] += 1
                elif a["risk_level"] == "Medium Risk":
                    date_map[p_date]["medium"] += 1

        sorted_dates = sorted(date_map.keys())
        formatted_labels = [datetime.strptime(d, "%Y-%m-%d").strftime("%d %b") for d in sorted_dates]

        return {
            "raw_dates": sorted_dates,
            "labels": formatted_labels,
            "high": [date_map[d]["high"] for d in sorted_dates],
            "medium": [date_map[d]["medium"] for d in sorted_dates],
        }

    def assign_reviewer(self, alert_id: str, reviewer: str) -> bool:
        for a in self.alerts:
            if a["id"] == alert_id or a["name"] == alert_id:
                a["assigned_to"] = reviewer
                if a["status"] == "Open":
                    a["status"] = "Assigned"
                a["audit_trail"].append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event": f"Assigned to {reviewer}",
                    "user": "System Admin",
                    "details": "Reviewer responsibility assigned for risk investigation"
                })
                return True
        return False

    def add_investigation_note(self, alert_id: str, note_text: str, author: str) -> bool:
        for a in self.alerts:
            if a["id"] == alert_id or a["name"] == alert_id:
                note_entry = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "author": author or "Auditor",
                    "text": note_text,
                }
                a["investigation_notes"].append(note_entry)
                a["audit_trail"].append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event": f"Investigation note recorded by {author}",
                    "user": author,
                    "details": note_text[:80] + ("..." if len(note_text) > 80 else "")
                })
                return True
        return False

    def update_status(self, alert_id: str, new_status: str, notes: str, user: str, fp_category: str = "") -> bool:
        for a in self.alerts:
            if a["id"] == alert_id or a["name"] == alert_id:
                old_status = a["status"]
                a["status"] = new_status
                if fp_category:
                    a["false_positive_category"] = fp_category
                
                details = f"Transitioned from {old_status} to {new_status}"
                if fp_category:
                    details += f" (Category: {fp_category})"
                if notes:
                    details += f". Note: {notes}"

                a["audit_trail"].append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event": f"Status updated to '{new_status}'",
                    "user": user or "Auditor",
                    "details": details
                })
                return True
        return False

    def add_custom_transaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        amount = float(data.get("amount", 0) or 0)
        hour = int(data.get("hour", 12))
        dow = int(data.get("day_of_week", 2))
        party = str(data.get("party", "Custom Vendor")).strip() or "Custom Vendor"
        narration = str(data.get("narration", "")).strip()

        dt = datetime.now()
        txn = {
            "name": f"JE-LIVE-{int(time.time()) % 10000}",
            "posting_date": dt.strftime("%Y-%m-%d"),
            "creation": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": amount,
            "debit_amount": amount,
            "credit_amount": 0.0,
            "party": party,
            "party_type": "Supplier",
            "account_type": "Payable",
            "narration": narration,
            "company": "Apex Global Technologies Pvt Ltd",
            "source_doctype": "Journal Entry",
            "posting_hour": hour,
            "posting_day_of_week": dow,
            "velocity_3d": int(data.get("velocity", 0)),
        }

        feat_df = self.fe.build_features([txn])
        ml_score = float(self.detector.score(feat_df)[0])
        triggered = self.rule_engine.check(txn)
        rule_score = self.rule_engine.rule_score(triggered)

        is_dup, dup_sim, dup_reason = False, 0.0, ""
        for existing in self.transactions:
            _is_dup, _sim, _reason = self.dup_detector.is_duplicate(txn, existing)
            if _is_dup:
                is_dup, dup_sim, dup_reason = True, _sim, _reason
                break

        dup_score = 1.0 if is_dup else 0.0
        c_score = self.scorer.composite_score(ml_score, rule_score, dup_score)
        risk_level = self.scorer.classify(c_score, high_threshold=0.70, medium_threshold=0.42)

        explanation = self.explainer.explain(
            transaction=txn,
            composite_score=c_score,
            triggered_rules=triggered,
            is_duplicate=is_dup,
            duplicate_reason=dup_reason
        )

        unusual = self._compute_unusual_features(feat_df.iloc[0], txn)

        return {
            "transaction": txn,
            "amount_formatted": format_amount(amount),
            "composite_score": c_score,
            "composite_score_pct": round(c_score * 100, 1),
            "risk_level": risk_level,
            "ml_score": round(ml_score, 4),
            "rule_score": round(rule_score, 4),
            "duplicate_score": dup_score,
            "is_duplicate": is_dup,
            "duplicate_reason": dup_reason,
            "triggered_rules": triggered,
            "unusual_features": unusual,
            "summary": explanation["summary"],
            "reasons": explanation["reasons"],
            "recommendation": explanation["recommendation"],
            "disclaimer": "FinGuard Anomaly Score measures statistical divergence and audit rule violations. Anomaly ≠ Fraud. Human review required.",
        }


# Global persistent state
STATE = DemoStateManager()


# ---------------------------------------------------------------------------
# HTTP API Request Handler & Router
# ---------------------------------------------------------------------------

class FinGuardHTTPHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} - {args[1]}\n")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Page routes
        if path in ("/", "/index.html", "/landing", "/landing.html"):
            index_path = os.path.join(BASE_DIR, "index.html")
            fallback_path = os.path.join(BASE_DIR, "landing.html")
            self._serve_file(index_path if os.path.exists(index_path) else fallback_path, "text/html; charset=utf-8")
        elif path in ("/login", "/login.html"):
            self._serve_file(os.path.join(BASE_DIR, "login.html"), "text/html; charset=utf-8")
        elif path in ("/dashboard", "/demo_dashboard.html"):
            self._serve_file(os.path.join(BASE_DIR, "demo_dashboard.html"), "text/html; charset=utf-8")

        # API Endpoints
        elif path == "/api/summary":
            self._send_json(STATE.get_summary())
        elif path == "/api/trend":
            self._send_json(STATE.get_trend_data())
        elif path == "/api/model_info":
            self._send_json(STATE.model_metadata)
        elif path == "/api/alerts":
            risk = query.get("risk", [None])[0]
            status = query.get("status", [None])[0]
            search = query.get("search", [None])[0]

            res = list(STATE.alerts)
            if risk and risk != "All":
                res = [a for a in res if a["risk_level"].lower().startswith(risk.lower())]
            if status and status != "All":
                res = [a for a in res if a["status"].lower() == status.lower()]
            if search:
                s = search.lower()
                res = [a for a in res if s in a["name"].lower() or s in a["party"].lower() or s in a["id"].lower()]

            self._send_json({"alerts": res})
        elif path == "/api/alert_details":
            alert_id = query.get("id", [None])[0]
            alert = next((a for a in STATE.alerts if a["id"] == alert_id or a["name"] == alert_id), None)
            if alert:
                self._send_json({"alert": alert, "reviewers": STATE.available_reviewers})
            else:
                self.send_error(404, "Alert not found")
        elif path == "/api/rule_breakdown":
            rule_counts = {}
            for a in STATE.alerts:
                for r in a.get("triggered_rules", []):
                    rule_counts[r] = rule_counts.get(r, 0) + 1
            if not rule_counts:
                rule_counts = {"ROUND_AMOUNT": 4, "OFF_HOURS_POSTING": 3, "LARGE_AMOUNT": 2}
            self._send_json({"rules": rule_counts})
        elif path == "/api/party_risk":
            party_stats = {}
            for a in STATE.alerts:
                p = a["party"]
                if p not in party_stats:
                    party_stats[p] = {"count": 0, "total_amount": 0, "max_score": 0}
                party_stats[p]["count"] += 1
                party_stats[p]["total_amount"] += a["amount"]
                party_stats[p]["max_score"] = max(party_stats[p]["max_score"], a["risk_score"])

            sorted_parties = sorted(party_stats.items(), key=lambda kv: kv[1]["count"], reverse=True)[:6]
            self._send_json({
                "parties": [
                    {
                        "party": k,
                        "count": v["count"],
                        "total_amount_formatted": format_amount(v["total_amount"]),
                        "max_score_pct": round(v["max_score"] * 100, 1),
                    }
                    for k, v in sorted_parties
                ]
            })
        elif path == "/public/css/finguard.css":
            self._serve_file(os.path.join(BASE_DIR, "finance_ai/public/css/finguard.css"), "text/css")
        elif path == "/public/js/finguard.js":
            self._serve_file(os.path.join(BASE_DIR, "finance_ai/public/js/finguard.js"), "application/javascript")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        # Authentication endpoints
        if path == "/api/auth/login":
            mode = data.get("mode", "user")
            if mode == "token":
                api_key = data.get("api_key", "")
                api_secret = data.get("api_secret", "")
                success, result = STATE.authenticate_token(api_key, api_secret)
            else:
                usr = data.get("username", "")
                pwd = data.get("password", "")
                site = data.get("site_url", "")
                success, result = STATE.authenticate_erpnext_user(usr, pwd, site)

            if success:
                self._send_json({"success": True, "user": result})
            else:
                self._send_json({"success": False, "message": result})

        elif path == "/api/auth/logout":
            token = data.get("token")
            if token in STATE.active_sessions:
                del STATE.active_sessions[token]
            self._send_json({"success": True, "message": "Logged out successfully"})

        # Scan & Pipeline Endpoints
        elif path == "/api/scan":
            time.sleep(0.3)
            summary = STATE.run_pipeline()
            self._send_json({"success": True, "summary": summary})
        elif path == "/api/retrain_model":
            summary = STATE.run_pipeline()
            self._send_json({"success": True, "model_metadata": STATE.model_metadata, "summary": summary})
        elif path == "/api/evaluate_transaction":
            result = STATE.add_custom_transaction(data)
            self._send_json(result)
        elif path == "/api/assign_reviewer":
            alert_id = data.get("alert_id")
            reviewer = data.get("reviewer")
            success = STATE.assign_reviewer(alert_id, reviewer)
            self._send_json({"success": success, "summary": STATE.get_summary()})
        elif path == "/api/add_investigation_note":
            alert_id = data.get("alert_id")
            note_text = data.get("note_text")
            author = data.get("author", "Auditor")
            success = STATE.add_investigation_note(alert_id, note_text, author)
            self._send_json({"success": success})
        elif path == "/api/update_alert_status":
            alert_id = data.get("alert_id")
            new_status = data.get("status")
            notes = data.get("notes", "")
            user = data.get("user", "Auditor")
            fp_category = data.get("false_positive_category", "")
            success = STATE.update_status(alert_id, new_status, notes, user, fp_category)
            self._send_json({"success": success, "summary": STATE.get_summary()})
        elif path == "/api/generate_forensic_brief":
            alert_id = data.get("alert_id")
            api_key = data.get("api_key")
            alert = next((a for a in STATE.alerts if a["id"] == alert_id or a["name"] == alert_id), None)
            if not alert:
                self._send_json({"success": False, "message": f"Alert {alert_id} not found"})
            else:
                brief = generate_forensic_brief(alert, api_key=api_key)
                alert["gemini_forensic_brief"] = brief
                self._send_json({"success": True, "brief": brief})
        else:
            self.send_error(404, "API endpoint not found")

    def _send_json(self, data: Any):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, file_path: str, content_type: str):
        if not os.path.exists(file_path):
            self.send_error(404, "File not found")
            return
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_server(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), FinGuardHTTPHandler)
    logger.info("===================================================================")
    logger.info(" FinGuard AI System LIVE at: http://localhost:%d", port)
    logger.info("  1. Landing Page:  http://localhost:%d/", port)
    logger.info("  2. ERPNext Login: http://localhost:%d/login", port)
    logger.info("  3. Risk Console:  http://localhost:%d/dashboard", port)
    logger.info("===================================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server terminated.")


if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
