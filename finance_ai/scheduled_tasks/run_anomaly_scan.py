"""
FinGuard AI — Scheduled Anomaly Scan Tasks
==========================================

This module provides the entry points called by Frappe's scheduler.

  run_full_scan  → called daily
                   - Retrains the Isolation Forest model on recent clean data
                   - Scans all transactions within the configured lookback window
                   - Creates/updates Financial Anomaly Alert records

  run_delta_scan → called hourly
                   - Scans only transactions posted in the past 2 hours
                   - Uses the previously trained model (no retraining)
                   - Fast path for near-real-time alerting
"""
from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import frappe
from frappe.utils import (
    add_days,
    add_to_date,
    cint,
    flt,
    now_datetime,
    today,
)

# ---------------------------------------------------------------------------
# Public scheduler entry points
# ---------------------------------------------------------------------------


def run_full_scan(
    company: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Daily full-scan entry point.

    Retrains the Isolation Forest model and scans all transactions within
    the configured lookback window (default 90 days).

    Args:
        company:   Filter by company. Defaults to all active companies.
        from_date: Override scan start date (YYYY-MM-DD).
        to_date:   Override scan end date (YYYY-MM-DD).  Defaults to today.

    Returns:
        Summary dict with keys: scan_log, alerts_created, alerts_updated,
        transactions_scanned, status.
    """
    scan_log_name: Optional[str] = None
    summary: Dict[str, Any] = {
        "scan_log": None,
        "alerts_created": 0,
        "alerts_updated": 0,
        "transactions_scanned": 0,
        "status": "failed",
    }

    try:
        config = _get_scan_config()

        # ── resolve date range ──────────────────────────────────────────────
        effective_to_date = to_date or today()
        effective_from_date = from_date or add_days(
            effective_to_date, -cint(config.get("lookback_days", 90))
        )

        # ── resolve companies ───────────────────────────────────────────────
        companies = _resolve_companies(company)
        if not companies:
            frappe.log_error(
                "FinGuard AI: No active companies found for full scan.",
                title="run_full_scan",
            )
            summary["status"] = "skipped"
            return summary

        # ── create scan log record ──────────────────────────────────────────
        scan_log_name = _create_scan_log(
            scan_type="Full",
            from_date=effective_from_date,
            to_date=effective_to_date,
            companies=companies,
        )
        summary["scan_log"] = scan_log_name

        # ── retrain model ───────────────────────────────────────────────────
        _retrain_model_if_needed(config, effective_from_date, effective_to_date, scan_log_name)

        # ── process each company ────────────────────────────────────────────
        total_alerts_created = 0
        total_alerts_updated = 0
        total_scanned = 0

        for comp in companies:
            try:
                transactions = _build_transactions_dataset(
                    company=comp,
                    from_date=effective_from_date,
                    to_date=effective_to_date,
                )
                if not transactions:
                    continue

                result = _run_scan_pipeline(
                    transactions=transactions,
                    config=config,
                    scan_log_name=scan_log_name,
                    mode="full",
                )
                total_alerts_created += result.get("alerts_created", 0)
                total_alerts_updated += result.get("alerts_updated", 0)
                total_scanned += len(transactions)

            except Exception as exc:
                frappe.log_error(
                    f"FinGuard AI: Error scanning company '{comp}': {exc}\n{traceback.format_exc()}",
                    title="run_full_scan.company_loop",
                )

        summary.update(
            {
                "alerts_created": total_alerts_created,
                "alerts_updated": total_alerts_updated,
                "transactions_scanned": total_scanned,
                "status": "success",
            }
        )
        _finalize_log(
            scan_log_name=scan_log_name,
            status="Completed",
            alerts_created=total_alerts_created,
            alerts_updated=total_alerts_updated,
        )

    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: run_full_scan failed: {exc}\n{traceback.format_exc()}",
            title="run_full_scan",
        )
        if scan_log_name:
            _finalize_log(
                scan_log_name=scan_log_name,
                status="Failed",
                alerts_created=summary["alerts_created"],
                alerts_updated=summary["alerts_updated"],
                error=str(exc),
            )
        summary["status"] = "failed"

    return summary


def run_delta_scan() -> Dict[str, Any]:
    """
    Hourly delta-scan entry point.

    Scans only transactions posted in the past 2 hours using the existing
    trained model (no retraining).  Designed for low-latency alerting.

    Returns:
        Summary dict with keys: scan_log, alerts_created, alerts_updated,
        transactions_scanned, status.
    """
    scan_log_name: Optional[str] = None
    summary: Dict[str, Any] = {
        "scan_log": None,
        "alerts_created": 0,
        "alerts_updated": 0,
        "transactions_scanned": 0,
        "status": "failed",
    }

    try:
        config = _get_scan_config()

        if not cint(config.get("enable_delta_scan", 1)):
            summary["status"] = "disabled"
            return summary

        now = now_datetime()
        to_dt = now.strftime("%Y-%m-%d %H:%M:%S")
        from_dt = add_to_date(now, hours=-2).strftime("%Y-%m-%d %H:%M:%S")

        companies = _resolve_companies(None)
        if not companies:
            summary["status"] = "skipped"
            return summary

        scan_log_name = _create_scan_log(
            scan_type="Delta",
            from_date=from_dt,
            to_date=to_dt,
            companies=companies,
        )
        summary["scan_log"] = scan_log_name

        total_alerts_created = 0
        total_alerts_updated = 0
        total_scanned = 0

        for comp in companies:
            try:
                transactions = _build_transactions_dataset(
                    company=comp,
                    from_date=from_dt,
                    to_date=to_dt,
                    use_creation_time=True,
                )
                if not transactions:
                    continue

                result = _run_scan_pipeline(
                    transactions=transactions,
                    config=config,
                    scan_log_name=scan_log_name,
                    mode="delta",
                )
                total_alerts_created += result.get("alerts_created", 0)
                total_alerts_updated += result.get("alerts_updated", 0)
                total_scanned += len(transactions)

            except Exception as exc:
                frappe.log_error(
                    f"FinGuard AI: Error in delta scan company '{comp}': {exc}\n{traceback.format_exc()}",
                    title="run_delta_scan.company_loop",
                )

        summary.update(
            {
                "alerts_created": total_alerts_created,
                "alerts_updated": total_alerts_updated,
                "transactions_scanned": total_scanned,
                "status": "success",
            }
        )
        _finalize_log(
            scan_log_name=scan_log_name,
            status="Completed",
            alerts_created=total_alerts_created,
            alerts_updated=total_alerts_updated,
        )

    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: run_delta_scan failed: {exc}\n{traceback.format_exc()}",
            title="run_delta_scan",
        )
        if scan_log_name:
            _finalize_log(
                scan_log_name=scan_log_name,
                status="Failed",
                alerts_created=summary["alerts_created"],
                alerts_updated=summary["alerts_updated"],
                error=str(exc),
            )
        summary["status"] = "failed"

    return summary


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_scan_config() -> Dict[str, Any]:
    """
    Load FinGuard Settings into a normalised config dict.

    Returns safe defaults if the Settings doc doesn't exist yet.
    """
    defaults: Dict[str, Any] = {
        "enable_ml_scan": 1,
        "enable_rule_scan": 1,
        "enable_duplicate_scan": 1,
        "enable_delta_scan": 1,
        "lookback_days": 90,
        "anomaly_threshold": 0.6,
        "duplicate_window_days": 3,
        "duplicate_amount_tolerance": 0.01,
        "large_amount_threshold": 500000,
        "round_amount_threshold": 1000,
        "off_hours_start": 20,
        "off_hours_end": 6,
        "ml_contamination": 0.05,
        "ml_n_estimators": 100,
        "alert_on_risk_levels": ["High", "Critical"],
        "retrain_on_full_scan": 1,
        "min_train_samples": 50,
    }

    try:
        if frappe.db.exists("FinGuard Settings", "FinGuard Settings"):
            doc = frappe.get_doc("FinGuard Settings", "FinGuard Settings")
            config = defaults.copy()
            for key in defaults:
                val = getattr(doc, key, None)
                if val is not None:
                    config[key] = val
            return config
    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: Could not load FinGuard Settings, using defaults. Error: {exc}",
            title="_get_scan_config",
        )

    return defaults


def _resolve_companies(company: Optional[str]) -> List[str]:
    """
    Return list of company names to scan.

    If `company` is given, return it as a single-element list.
    Otherwise return all active companies from the Company master.
    """
    if company:
        return [company]

    try:
        rows = frappe.db.get_all(
            "Company",
            filters={"is_group": 0},
            pluck="name",
        )
        return rows or []
    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: Failed to fetch company list: {exc}",
            title="_resolve_companies",
        )
        return []


def _create_scan_log(
    scan_type: str,
    from_date: str,
    to_date: str,
    companies: List[str],
) -> str:
    """
    Insert a new Anomaly Model Log record (status=Running) and return its name.
    """
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Anomaly Model Log",
                "scan_type": scan_type,
                "scan_from_date": from_date,
                "scan_to_date": to_date,
                "companies_scanned": ", ".join(companies),
                "status": "Running",
                "started_at": now_datetime(),
                "alerts_created": 0,
                "alerts_updated": 0,
                "transactions_scanned": 0,
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: Failed to create Anomaly Model Log: {exc}\n{traceback.format_exc()}",
            title="_create_scan_log",
        )
        return ""


def _retrain_model_if_needed(
    config: Dict[str, Any],
    from_date: str,
    to_date: str,
    scan_log_name: str,
) -> None:
    """
    Trigger model retraining if the config flag is set.

    Delegates to the ModelTrainer service inside the anomaly_engine package.
    Logs the outcome to the Anomaly Model Log without raising.
    """
    if not cint(config.get("retrain_on_full_scan", 1)):
        return

    try:
        from finance_ai.anomaly_engine.model_trainer import ModelTrainer

        trainer = ModelTrainer(config=config)
        training_result = trainer.retrain(from_date=from_date, to_date=to_date)

        if scan_log_name:
            try:
                frappe.db.set_value(
                    "Anomaly Model Log",
                    scan_log_name,
                    {
                        "model_version": training_result.get("model_version", ""),
                        "training_samples": training_result.get("samples_used", 0),
                    },
                )
                frappe.db.commit()
            except Exception:
                pass  # non-critical — don't abort the scan

    except ImportError:
        # ModelTrainer not yet available — skip silently
        frappe.logger().warning(
            "FinGuard AI: ModelTrainer not available, skipping retraining."
        )
    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: Model retraining failed (scan will continue): {exc}\n{traceback.format_exc()}",
            title="_retrain_model_if_needed",
        )


def _build_transactions_dataset(
    company: str,
    from_date: str,
    to_date: str,
    use_creation_time: bool = False,
) -> List[Dict[str, Any]]:
    """
    Query Journal Entry and Payment Entry records from ERPNext.

    Args:
        company:           Company to fetch transactions for.
        from_date:         Start date/datetime string.
        to_date:           End date/datetime string.
        use_creation_time: If True filter on `creation` (for delta scans);
                           otherwise filter on `posting_date`.

    Returns:
        List of flat dicts representing individual transaction lines.
    """
    transactions: List[Dict[str, Any]] = []

    # ── Journal Entries ─────────────────────────────────────────────────────
    try:
        date_field = "creation" if use_creation_time else "posting_date"
        je_rows = frappe.db.sql(
            f"""
            SELECT
                je.name,
                je.posting_date,
                je.total_debit         AS amount,
                jea.debit_in_account_currency  AS debit_amount,
                jea.credit_in_account_currency AS credit_amount,
                jea.party              AS party,
                jea.party_type         AS party_type,
                acc.account_type       AS account_type,
                je.user_remark         AS narration,
                je.creation,
                je.company,
                je.cheque_no           AS reference_no,
                je.cheque_date         AS reference_date,
                'Journal Entry'        AS doctype
            FROM
                `tabJournal Entry`      je
            LEFT JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
            LEFT JOIN `tabAccount`      acc ON acc.name = jea.account
            WHERE
                je.docstatus = 1
                AND je.company = %(company)s
                AND je.{date_field} BETWEEN %(from_date)s AND %(to_date)s
            ORDER BY je.{date_field} ASC
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
            as_dict=True,
        )
        transactions.extend(je_rows or [])
    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: Failed to fetch Journal Entries for '{company}': {exc}",
            title="_build_transactions_dataset.journal_entry",
        )

    # ── Payment Entries ─────────────────────────────────────────────────────
    try:
        date_field = "creation" if use_creation_time else "posting_date"
        pe_rows = frappe.db.sql(
            f"""
            SELECT
                pe.name,
                pe.posting_date,
                pe.paid_amount          AS amount,
                pe.paid_amount          AS debit_amount,
                0                       AS credit_amount,
                pe.party                AS party,
                pe.party_type           AS party_type,
                'Payment'               AS account_type,
                pe.remarks              AS narration,
                pe.creation,
                pe.company,
                pe.reference_no,
                pe.reference_date,
                'Payment Entry'         AS doctype
            FROM
                `tabPayment Entry` pe
            WHERE
                pe.docstatus = 1
                AND pe.company = %(company)s
                AND pe.{date_field} BETWEEN %(from_date)s AND %(to_date)s
            ORDER BY pe.{date_field} ASC
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
            as_dict=True,
        )
        transactions.extend(pe_rows or [])
    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: Failed to fetch Payment Entries for '{company}': {exc}",
            title="_build_transactions_dataset.payment_entry",
        )

    return transactions


def _run_scan_pipeline(
    transactions: List[Dict[str, Any]],
    config: Dict[str, Any],
    scan_log_name: str,
    mode: str = "full",
) -> Dict[str, Any]:
    """
    Core analysis pipeline:
        1. Feature Engineering  — converts raw rows into ML feature vectors
        2. ML Scoring           — Isolation Forest anomaly scores
        3. Rule Engine          — deterministic rule-based flags
        4. Duplicate Detection  — near-duplicate transaction detection
        5. Composite Scoring    — weighted aggregation of all signals
        6. Explainability       — human-readable reasons
        7. Alert Creation       — upsert Financial Anomaly Alert records

    Args:
        transactions:   List of transaction dicts from ERPNext.
        config:         Scan configuration dict from _get_scan_config().
        scan_log_name:  Name of the Anomaly Model Log record.
        mode:           'full' or 'delta'.

    Returns:
        Dict with alerts_created and alerts_updated counts.
    """
    alerts_created = 0
    alerts_updated = 0

    try:
        import pandas as pd

        from finance_ai.anomaly_engine.duplicate_detector import DuplicateDetector
        from finance_ai.anomaly_engine.explainer import AnomalyExplainer
        from finance_ai.anomaly_engine.features import FeatureEngineer
        from finance_ai.anomaly_engine.rule_engine import RuleEngine
        from finance_ai.anomaly_engine.scorer import AnomalyScorer

        df = pd.DataFrame(transactions)
        if df.empty:
            return {"alerts_created": 0, "alerts_updated": 0}

        # 1. Feature Engineering
        feature_engineer = FeatureEngineer(config=config)
        feature_df = feature_engineer.build_features(df)

        # 2. ML Scoring (skip in delta mode if no model exists)
        ml_scores: List[float] = []
        if cint(config.get("enable_ml_scan", 1)):
            try:
                from finance_ai.anomaly_engine.ml_engine import IsolationForestEngine

                ml_engine = IsolationForestEngine(config=config)
                ml_scores = ml_engine.score(feature_df)
            except Exception as exc:
                frappe.log_error(
                    f"FinGuard AI: ML scoring failed, using 0.0 scores: {exc}",
                    title="_run_scan_pipeline.ml_scoring",
                )
                ml_scores = [0.0] * len(df)
        else:
            ml_scores = [0.0] * len(df)

        # 3. Rule Engine
        rule_results: List[Dict] = []
        if cint(config.get("enable_rule_scan", 1)):
            rule_engine = RuleEngine(config=config)
            for _, row in feature_df.iterrows():
                rule_results.append(rule_engine.evaluate(row.to_dict()))
        else:
            rule_results = [{"score": 0.0, "triggered_rules": []}] * len(df)

        # 4. Duplicate Detection
        dup_flags: List[bool] = [False] * len(df)
        if cint(config.get("enable_duplicate_scan", 1)):
            try:
                dup_detector = DuplicateDetector(config=config)
                dup_flags = dup_detector.detect(df)
            except Exception as exc:
                frappe.log_error(
                    f"FinGuard AI: Duplicate detection failed: {exc}",
                    title="_run_scan_pipeline.duplicate",
                )

        # 5. Composite Scoring + 6. Explainability + 7. Alert upsert
        scorer = AnomalyScorer(config=config)
        explainer = AnomalyExplainer(config=config)
        alert_risk_levels = config.get("alert_on_risk_levels", ["High", "Critical"])

        for i, tx in enumerate(transactions):
            try:
                ml_score = ml_scores[i] if i < len(ml_scores) else 0.0
                rule_result = rule_results[i] if i < len(rule_results) else {"score": 0.0, "triggered_rules": []}
                is_duplicate = dup_flags[i] if i < len(dup_flags) else False

                score_result = scorer.composite_score(
                    ml_score=ml_score,
                    rule_score=rule_result.get("score", 0.0),
                    is_duplicate=is_duplicate,
                    triggered_rules=rule_result.get("triggered_rules", []),
                )

                # Only create alerts for configured risk levels
                if score_result.get("risk_level") not in alert_risk_levels:
                    continue

                # Attach explanation
                score_result["explanation"] = explainer.explain(
                    transaction=tx,
                    score_result=score_result,
                    triggered_rules=rule_result.get("triggered_rules", []),
                    is_duplicate=is_duplicate,
                )

                result = _upsert_alert(
                    transaction_data=tx,
                    score_result=score_result,
                    scan_log_name=scan_log_name,
                )
                if result == "created":
                    alerts_created += 1
                elif result == "updated":
                    alerts_updated += 1

            except Exception as exc:
                frappe.log_error(
                    f"FinGuard AI: Error processing transaction '{tx.get('name', 'unknown')}': {exc}",
                    title="_run_scan_pipeline.tx_loop",
                )

    except ImportError as exc:
        frappe.log_error(
            f"FinGuard AI: anomaly_engine import error — pipeline cannot run: {exc}",
            title="_run_scan_pipeline",
        )
    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: Unexpected pipeline error: {exc}\n{traceback.format_exc()}",
            title="_run_scan_pipeline",
        )

    return {"alerts_created": alerts_created, "alerts_updated": alerts_updated}


def _upsert_alert(
    transaction_data: Dict[str, Any],
    score_result: Dict[str, Any],
    scan_log_name: str,
) -> str:
    """
    Create or update a Financial Anomaly Alert record.

    Returns:
        'created', 'updated', or 'skipped' string indicating what happened.
    """
    tx_name = transaction_data.get("name", "")
    tx_doctype = transaction_data.get("doctype", "Journal Entry")

    if not tx_name:
        return "skipped"

    try:
        existing = frappe.db.get_value(
            "Financial Anomaly Alert",
            {
                "reference_doctype": tx_doctype,
                "reference_name": tx_name,
            },
            "name",
        )

        alert_data = {
            "reference_doctype": tx_doctype,
            "reference_name": tx_name,
            "posting_date": transaction_data.get("posting_date"),
            "amount": flt(transaction_data.get("amount", 0)),
            "party": transaction_data.get("party", ""),
            "party_type": transaction_data.get("party_type", ""),
            "narration": (transaction_data.get("narration", "") or "")[:500],
            "company": transaction_data.get("company", ""),
            "composite_score": flt(score_result.get("composite_score", 0)),
            "ml_score": flt(score_result.get("ml_score", 0)),
            "rule_score": flt(score_result.get("rule_score", 0)),
            "risk_level": score_result.get("risk_level", "Low"),
            "triggered_rules": ", ".join(score_result.get("triggered_rules", [])),
            "is_duplicate": cint(score_result.get("is_duplicate", 0)),
            "explanation": score_result.get("explanation", ""),
            "recommendation": score_result.get("recommendation", ""),
            "scan_log": scan_log_name,
            "last_scanned_at": now_datetime(),
        }

        if existing:
            # Preserve investigation status — only update scores/explanation
            doc = frappe.get_doc("Financial Anomaly Alert", existing)
            if doc.status in ("Resolved", "False Positive"):
                return "skipped"  # don't overwrite resolved alerts

            for field, value in alert_data.items():
                setattr(doc, field, value)
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            return "updated"
        else:
            alert_data.update(
                {
                    "doctype": "Financial Anomaly Alert",
                    "status": "Open",
                    "alert_date": now_datetime(),
                }
            )
            doc = frappe.get_doc(alert_data)
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            return "created"

    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: _upsert_alert failed for '{tx_name}': {exc}\n{traceback.format_exc()}",
            title="_upsert_alert",
        )
        return "skipped"


def _finalize_log(
    scan_log_name: str,
    status: str,
    alerts_created: int,
    alerts_updated: int,
    error: Optional[str] = None,
) -> None:
    """
    Update the Anomaly Model Log record with final counts and status.

    Args:
        scan_log_name:  Name of the log document.
        status:         'Completed' or 'Failed'.
        alerts_created: Number of new alert records created.
        alerts_updated: Number of existing alert records updated.
        error:          Optional error message string (for failed scans).
    """
    if not scan_log_name:
        return

    try:
        update_dict = {
            "status": status,
            "completed_at": now_datetime(),
            "alerts_created": alerts_created,
            "alerts_updated": alerts_updated,
        }
        if error:
            update_dict["error_message"] = str(error)[:1000]

        frappe.db.set_value(
            "Financial Anomaly Alert" if False else "Anomaly Model Log",
            scan_log_name,
            update_dict,
        )
        frappe.db.commit()

    except Exception as exc:
        frappe.log_error(
            f"FinGuard AI: _finalize_log failed for '{scan_log_name}': {exc}",
            title="_finalize_log",
        )
