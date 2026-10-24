"""
FinGuard AI — Frappe Integration Layer (Scanner)
=================================================
Provides the Frappe document-event hooks and scheduled-task entry points.

quick_scan(doc, method)  → called on Journal Entry / Payment Entry on_submit
full_scan(...)           → called by scheduler (daily) or manual trigger
delta_scan()             → called by scheduler (hourly)

All Frappe imports are wrapped in try/except so the anomaly_engine modules
can still be unit-tested without a live Frappe instance.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import frappe
    from frappe.utils import today, add_days, now_datetime, getdate
    _FRAPPE_AVAILABLE = True
except ImportError:
    _FRAPPE_AVAILABLE = False
    frappe = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public Frappe event hooks
# ---------------------------------------------------------------------------

def quick_scan(doc: Any, method: str) -> None:
    """
    Frappe document-event handler for Journal Entry and Payment Entry on_submit.

    Runs only the rule engine (fast, synchronous) so as not to block the
    document submission flow.  Creates a Financial Anomaly Alert if any
    rule triggers with a score above 0.30.

    Parameters
    ----------
    doc:
        The Frappe document being submitted.
    method:
        Event name ('on_submit').
    """
    if not _FRAPPE_AVAILABLE:
        return

    try:
        transaction = _doc_to_transaction(doc)
        if not transaction:
            return

        from finance_ai.anomaly_engine.rule_engine import RuleEngine
        from finance_ai.anomaly_engine.scorer import AnomalyScorer

        rule_engine = RuleEngine()
        triggered   = rule_engine.check(transaction)
        rule_score  = rule_engine.rule_score(triggered)

        # Quick-scan only creates alerts for moderate+ rule scores
        if rule_score < 0.30 or not triggered:
            return

        # Lightweight composite: treat ML score as rule_score, no dup check
        scorer = AnomalyScorer(ml_weight=40, rule_weight=35, duplicate_weight=25)
        c_score = scorer.composite_score(
            ml_score=rule_score,
            rule_score=rule_score,
            duplicate_score=0.0,
        )
        risk_level = scorer.classify(c_score)

        from finance_ai.anomaly_engine.explainer import AnomalyExplainer
        explainer   = AnomalyExplainer()
        explanation = explainer.explain(
            transaction=transaction,
            composite_score=c_score,
            triggered_rules=triggered,
            is_duplicate=False,
        )

        score_result = {
            "ml_score":        rule_score,
            "rule_score":      rule_score,
            "duplicate_score": 0.0,
            "composite_score": c_score,
            "risk_level":      risk_level,
            "triggered_rules": triggered,
            "is_duplicate":    False,
            "duplicate_of":    "",
            "duplicate_similarity": 0.0,
            **explanation,
        }

        _upsert_alert(transaction, score_result, scan_log_name="quick-scan")

    except Exception:  # pylint: disable=broad-except
        if _FRAPPE_AVAILABLE:
            frappe.log_error(frappe.get_traceback(), "FinGuard: quick_scan failed")


def full_scan(
    company:   Optional[str] = None,
    from_date: Optional[str] = None,
    to_date:   Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run a complete ML + rule + duplicate scan over a date range.

    Called by the daily scheduler and by the manual scan button on the
    FinGuard dashboard.

    Returns
    -------
    dict
        Summary: transactions_scanned, alerts_created, alerts_updated,
        status, scan_log.
    """
    if not _FRAPPE_AVAILABLE:
        return {"status": "skipped", "reason": "Frappe not available"}

    log_name = _create_scan_log("Full Scan", company, from_date, to_date)

    try:
        cfg = _get_scan_config()
        if not cfg.get("enabled", True):
            _finalize_log(log_name, "Completed", 0, 0)
            return {"status": "disabled"}

        if not to_date:
            to_date = today()
        if not from_date:
            from_date = add_days(to_date, -int(cfg.get("lookback_days", 90)))

        transactions = _build_transactions_dataset(company, from_date, to_date)
        if not transactions:
            _finalize_log(log_name, "Completed", 0, 0)
            return {"status": "ok", "transactions_scanned": 0, "alerts_created": 0, "alerts_updated": 0}

        result = _run_scan_pipeline(transactions, cfg, log_name, mode="full")
        _finalize_log(log_name, "Completed", result["alerts_created"], result["alerts_updated"])
        return result

    except Exception:
        frappe.log_error(frappe.get_traceback(), "FinGuard: full_scan failed")
        _finalize_log(log_name, "Failed", 0, 0, error=frappe.get_traceback())
        return {"status": "error"}


def delta_scan() -> Dict[str, Any]:
    """
    Run a fast delta scan covering only the last 2 hours.

    Called by the hourly scheduler.  Uses rule engine only (no ML retrain).
    """
    if not _FRAPPE_AVAILABLE:
        return {"status": "skipped"}

    try:
        cfg       = _get_scan_config()
        if not cfg.get("enabled", True):
            return {"status": "disabled"}

        to_date   = today()
        from_date = add_days(to_date, -1)  # last 24 h is sufficient for delta
        transactions = _build_transactions_dataset(None, from_date, to_date)
        if not transactions:
            return {"status": "ok", "transactions_scanned": 0}

        return _run_scan_pipeline(transactions, cfg, "delta-scan", mode="delta")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "FinGuard: delta_scan failed")
        return {"status": "error"}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_scan_config() -> Dict[str, Any]:
    """Load FinGuard Settings into a plain dict (safe defaults if missing)."""
    defaults = {
        "enabled":                      True,
        "scan_mode":                    "Hybrid",
        "ml_weight":                    40,
        "rule_weight":                  35,
        "duplicate_weight":             25,
        "lookback_days":                90,
        "large_amount_threshold":       500_000,
        "duplicate_similarity_threshold": 85,
        "duplicate_date_window":        3,
        "high_risk_threshold":          0.75,
        "medium_risk_threshold":        0.45,
        "anomaly_threshold":            0.05,
        "model_path":                   "",
    }
    if not _FRAPPE_AVAILABLE:
        return defaults
    try:
        settings = frappe.get_single("FinGuard Settings")
        return {
            "enabled":                      bool(settings.enabled),
            "scan_mode":                    settings.scan_mode or "Hybrid",
            "ml_weight":                    int(settings.ml_weight or 40),
            "rule_weight":                  int(settings.rule_weight or 35),
            "duplicate_weight":             int(settings.duplicate_weight or 25),
            "lookback_days":                int(settings.lookback_days or 90),
            "large_amount_threshold":       float(settings.large_amount_threshold or 500_000),
            "duplicate_similarity_threshold": int(settings.duplicate_similarity_threshold or 85),
            "duplicate_date_window":        int(settings.duplicate_date_window or 3),
            "high_risk_threshold":          float(settings.high_risk_threshold or 0.75),
            "medium_risk_threshold":        float(settings.medium_risk_threshold or 0.45),
            "anomaly_threshold":            float(settings.anomaly_threshold or 0.05),
            "model_path":                   settings.model_path or "",
        }
    except Exception:
        return defaults


def _build_transactions_dataset(
    company:   Optional[str],
    from_date: str,
    to_date:   str,
) -> List[Dict[str, Any]]:
    """Query Journal Entry + Payment Entry records from ERPNext."""
    if not _FRAPPE_AVAILABLE:
        return []

    filters = [
        ["posting_date", "between", [from_date, to_date]],
        ["docstatus", "=", 1],
    ]
    if company:
        filters.append(["company", "=", company])

    fields = [
        "name", "posting_date", "creation", "company",
        "total_debit as debit_amount", "total_credit as credit_amount",
        "total_debit as amount", "remark as narration",
    ]

    transactions: List[Dict[str, Any]] = []

    # Journal Entries
    try:
        jes = frappe.db.get_all(
            "Journal Entry",
            filters=filters,
            fields=fields + ["voucher_type"],
        )
        for je in jes:
            je["source_doctype"] = "Journal Entry"
            je["party"]          = je.get("pay_to_recd_from", "")
            je["party_type"]     = ""
            je["account_type"]   = ""
            je["posting_hour"]   = 12  # fallback; will be overridden by creation
            je["posting_day_of_week"] = 0
            je["velocity_3d"]    = 0
            je["velocity_7d"]    = 0
            transactions.append(dict(je))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "FinGuard: JE query failed")

    # Payment Entries
    try:
        pes = frappe.db.get_all(
            "Payment Entry",
            filters=filters,
            fields=[
                "name", "posting_date", "creation", "company",
                "paid_amount as amount", "paid_amount as debit_amount",
                "received_amount as credit_amount",
                "party", "party_type", "remarks as narration",
            ],
        )
        for pe in pes:
            pe["source_doctype"] = "Payment Entry"
            pe["account_type"]   = ""
            pe["posting_hour"]   = 12
            pe["posting_day_of_week"] = 0
            pe["velocity_3d"]    = 0
            pe["velocity_7d"]    = 0
            transactions.append(dict(pe))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "FinGuard: PE query failed")

    return transactions


def _run_scan_pipeline(
    transactions: List[Dict[str, Any]],
    cfg:          Dict[str, Any],
    scan_log_name: str,
    mode:         str = "full",
) -> Dict[str, Any]:
    """
    Core ML + rule + duplicate scan pipeline.

    Returns summary dict: transactions_scanned, alerts_created, alerts_updated.
    """
    from finance_ai.anomaly_engine.features import FeatureEngineer
    from finance_ai.anomaly_engine.rule_engine import RuleEngine
    from finance_ai.anomaly_engine.duplicate_detector import DuplicateDetector
    from finance_ai.anomaly_engine.isolation_forest import IsolationForestDetector
    from finance_ai.anomaly_engine.scorer import AnomalyScorer

    scan_mode = cfg.get("scan_mode", "Hybrid")

    # Feature engineering
    fe          = FeatureEngineer()
    feature_df  = fe.build_features(transactions)

    # ML model
    detector = IsolationForestDetector(contamination=cfg.get("anomaly_threshold", 0.05))
    if mode == "full" and scan_mode in ("Hybrid", "ML Only") and len(transactions) >= 10:
        detector.fit(feature_df)
        ml_scores = detector.score(feature_df)
    else:
        ml_scores = [0.5] * len(transactions)

    # Rule engine
    rule_engine = RuleEngine(config={
        "large_amount_threshold": cfg.get("large_amount_threshold", 500_000),
    })

    # Duplicate detector
    dup_detector = DuplicateDetector(
        similarity_threshold=cfg.get("duplicate_similarity_threshold", 85),
        date_window_days=cfg.get("duplicate_date_window", 3),
    )
    dup_results = {d["transaction_id"]: d for d in dup_detector.find_duplicates(transactions)}

    # Scorer + explainer
    scorer = AnomalyScorer(
        ml_weight=cfg.get("ml_weight", 40),
        rule_weight=cfg.get("rule_weight", 35),
        duplicate_weight=cfg.get("duplicate_weight", 25),
    )

    alerts_created = 0
    alerts_updated = 0

    for i, txn in enumerate(transactions):
        try:
            ml_score  = float(ml_scores[i]) if i < len(ml_scores) else 0.5
            triggered = rule_engine.check(txn)
            rule_score = rule_engine.rule_score(triggered)

            dup_info  = dup_results.get(txn.get("name", ""), {})
            is_dup    = bool(dup_info)
            dup_score = 1.0 if is_dup else 0.0

            c_score    = scorer.composite_score(ml_score, rule_score, dup_score)
            risk_level = scorer.classify(
                c_score,
                high_threshold=cfg.get("high_risk_threshold", 0.75),
                medium_threshold=cfg.get("medium_risk_threshold", 0.45),
            )

            # Only persist alerts above a minimum threshold
            if c_score < 0.20 and not triggered and not is_dup:
                continue

            from finance_ai.anomaly_engine.explainer import AnomalyExplainer
            explainer   = AnomalyExplainer()
            explanation = explainer.explain(
                transaction=txn,
                composite_score=c_score,
                triggered_rules=triggered,
                is_duplicate=is_dup,
                duplicate_reason=dup_info.get("reason", ""),
            )

            score_result = {
                "ml_score":           round(ml_score, 6),
                "rule_score":         round(rule_score, 6),
                "duplicate_score":    dup_score,
                "composite_score":    c_score,
                "risk_level":         risk_level,
                "triggered_rules":    triggered,
                "is_duplicate":       is_dup,
                "duplicate_of":       dup_info.get("duplicate_of", ""),
                "duplicate_similarity": dup_info.get("similarity", 0.0),
                **explanation,
            }

            created = _upsert_alert(txn, score_result, scan_log_name)
            if created:
                alerts_created += 1
            else:
                alerts_updated += 1

        except Exception:  # pylint: disable=broad-except
            if _FRAPPE_AVAILABLE:
                frappe.log_error(frappe.get_traceback(), f"FinGuard: error scoring {txn.get('name')}")

    return {
        "status":              "ok",
        "transactions_scanned": len(transactions),
        "alerts_created":      alerts_created,
        "alerts_updated":      alerts_updated,
        "scan_log":            scan_log_name,
    }


def _upsert_alert(
    transaction:  Dict[str, Any],
    score_result: Dict[str, Any],
    scan_log_name: str,
) -> bool:
    """
    Create or update a Financial Anomaly Alert for a transaction.

    Returns True if a new record was created, False if updated.
    """
    if not _FRAPPE_AVAILABLE:
        return False

    source_doctype = transaction.get("source_doctype", "Journal Entry")
    source_name    = transaction.get("name", "")

    try:
        existing = frappe.db.get_value(
            "Financial Anomaly Alert",
            {"source_doctype": source_doctype, "source_document": source_name},
            "name",
        )

        if existing:
            doc = frappe.get_doc("Financial Anomaly Alert", existing)
            # Only update if score changed meaningfully
            if abs(float(doc.risk_score or 0) - score_result["composite_score"]) > 0.01:
                doc.risk_score         = score_result["composite_score"]
                doc.ml_score           = score_result["ml_score"]
                doc.rule_score         = score_result["rule_score"]
                doc.duplicate_score    = score_result["duplicate_score"]
                doc.risk_level         = score_result["risk_level"]
                doc.triggered_rules    = json.dumps(score_result["triggered_rules"])
                doc.summary            = score_result["summary"]
                doc.reasons            = "\n".join(score_result.get("reasons", []))
                doc.recommendation     = score_result["recommendation"]
                doc.is_duplicate       = int(score_result["is_duplicate"])
                doc.duplicate_of       = score_result.get("duplicate_of", "")
                doc.duplicate_similarity = score_result.get("duplicate_similarity", 0)
                doc.scan_run           = scan_log_name
                doc.save(ignore_permissions=True)
            return False

        doc = frappe.new_doc("Financial Anomaly Alert")
        doc.source_doctype      = source_doctype
        doc.source_document     = source_name
        doc.company             = transaction.get("company", "")
        doc.posting_date        = transaction.get("posting_date")
        doc.amount              = transaction.get("amount", 0)
        doc.party_type          = transaction.get("party_type", "")
        doc.party               = transaction.get("party", "")
        doc.risk_score          = score_result["composite_score"]
        doc.ml_score            = score_result["ml_score"]
        doc.rule_score          = score_result["rule_score"]
        doc.duplicate_score     = score_result["duplicate_score"]
        doc.risk_level          = score_result["risk_level"]
        doc.triggered_rules     = json.dumps(score_result["triggered_rules"])
        doc.summary             = score_result["summary"]
        doc.reasons             = "\n".join(score_result.get("reasons", []))
        doc.recommendation      = score_result["recommendation"]
        doc.is_duplicate        = int(score_result["is_duplicate"])
        doc.duplicate_of        = score_result.get("duplicate_of", "")
        doc.duplicate_similarity= score_result.get("duplicate_similarity", 0)
        doc.status              = "Open"
        doc.scan_run            = scan_log_name
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return True

    except Exception:
        frappe.log_error(frappe.get_traceback(), f"FinGuard: _upsert_alert failed for {source_name}")
        return False


def _doc_to_transaction(doc: Any) -> Optional[Dict[str, Any]]:
    """Convert a Frappe document to a transaction dict for the scanner."""
    if not _FRAPPE_AVAILABLE:
        return None
    try:
        from frappe.utils import get_datetime
        created = get_datetime(doc.creation)
        return {
            "name":             doc.name,
            "source_doctype":   doc.doctype,
            "posting_date":     str(doc.posting_date),
            "creation":         str(doc.creation),
            "company":          doc.company,
            "amount":           float(getattr(doc, "total_debit", 0) or getattr(doc, "paid_amount", 0) or 0),
            "debit_amount":     float(getattr(doc, "total_debit", 0) or 0),
            "credit_amount":    float(getattr(doc, "total_credit", 0) or getattr(doc, "received_amount", 0) or 0),
            "party":            getattr(doc, "party", "") or getattr(doc, "pay_to_recd_from", ""),
            "party_type":       getattr(doc, "party_type", ""),
            "narration":        getattr(doc, "remark", "") or getattr(doc, "remarks", ""),
            "account_type":     "",
            "posting_hour":     created.hour if created else 12,
            "posting_day_of_week": created.weekday() if created else 0,
            "velocity_3d":      0,
            "velocity_7d":      0,
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "FinGuard: _doc_to_transaction failed")
        return None


def _create_scan_log(
    scan_type: str,
    company:   Optional[str],
    from_date: Optional[str],
    to_date:   Optional[str],
) -> str:
    """Create an Anomaly Model Log record and return its name."""
    if not _FRAPPE_AVAILABLE:
        return "offline"
    try:
        log = frappe.new_doc("Anomaly Model Log")
        log.scan_type  = scan_type
        log.company    = company or ""
        log.from_date  = from_date
        log.to_date    = to_date
        log.scan_start = now_datetime()
        log.status     = "Running"
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log.name
    except Exception:
        return "unknown"


def _finalize_log(
    log_name:       str,
    status:         str,
    alerts_created: int,
    alerts_updated: int,
    error:          Optional[str] = None,
) -> None:
    """Update the Anomaly Model Log with final scan results."""
    if not _FRAPPE_AVAILABLE or log_name in ("offline", "unknown"):
        return
    try:
        log = frappe.get_doc("Anomaly Model Log", log_name)
        log.scan_end       = now_datetime()
        log.status         = status
        log.alerts_created = alerts_created
        log.alerts_updated = alerts_updated
        if error:
            log.error_log = error
        log.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass
