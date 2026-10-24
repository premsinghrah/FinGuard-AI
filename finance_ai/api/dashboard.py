# Copyright (c) 2024, FinGuard AI and contributors
# For license information, please see license.txt

"""
FinGuard AI — Dashboard API Endpoints
Provides whitelisted server-side methods for the Risk Dashboard page.
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, getdate, flt, nowdate


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _date_defaults(from_date, to_date, days=30):
    """Return (from_date, to_date) with sensible defaults."""
    if not to_date:
        to_date = today()
    if not from_date:
        from_date = add_days(to_date, -int(days))
    return getdate(from_date), getdate(to_date)


def _company_filter(company):
    """Return a dict suitable for frappe.db.get_list filters."""
    if company:
        return {"company": company}
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_dashboard_summary(company=None, from_date=None, to_date=None):
    """
    Return KPI summary for the FinGuard dashboard.

    Returns a dict with:
        total_alerts, high_risk_count, medium_risk_count, low_risk_count,
        open_alerts, resolved_alerts, false_positives, total_amount_at_risk
    """
    try:
        from_date, to_date = _date_defaults(from_date, to_date)

        base_filters = [
            ["posting_date", "between", [from_date, to_date]],
        ]
        if company:
            base_filters.append(["company", "=", company])

        alerts = frappe.db.get_all(
            "Financial Anomaly Alert",
            filters=base_filters,
            fields=["name", "risk_level", "status", "transaction_amount"],
        )

        total_alerts     = len(alerts)
        high_risk_count  = sum(1 for a in alerts if a.risk_level == "High")
        medium_risk_count= sum(1 for a in alerts if a.risk_level == "Medium")
        low_risk_count   = sum(1 for a in alerts if a.risk_level == "Low")
        open_alerts      = sum(1 for a in alerts if a.status in ("Open", "Under Review"))
        resolved_alerts  = sum(1 for a in alerts if a.status == "Resolved")
        false_positives  = sum(1 for a in alerts if a.status == "False Positive")
        total_amount_at_risk = flt(
            sum(flt(a.transaction_amount) for a in alerts if a.risk_level in ("High", "Medium"))
        )

        return {
            "total_alerts":        total_alerts,
            "high_risk_count":     high_risk_count,
            "medium_risk_count":   medium_risk_count,
            "low_risk_count":      low_risk_count,
            "open_alerts":         open_alerts,
            "resolved_alerts":     resolved_alerts,
            "false_positives":     false_positives,
            "total_amount_at_risk": total_amount_at_risk,
            "from_date":           str(from_date),
            "to_date":             str(to_date),
        }

    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "FinGuard: get_dashboard_summary failed")
        frappe.throw(_("Failed to load dashboard summary: {0}").format(str(exc)))


@frappe.whitelist()
def get_risk_trend(company=None, days=30):
    """
    Return daily risk score trend for chart rendering.

    Returns a list of dicts: [{date, high, medium, low}, ...]
    """
    try:
        days = int(days)
        to_date   = getdate(today())
        from_date = add_days(to_date, -days)

        filters = [["posting_date", "between", [from_date, to_date]]]
        if company:
            filters.append(["company", "=", company])

        alerts = frappe.db.get_all(
            "Financial Anomaly Alert",
            filters=filters,
            fields=["posting_date", "risk_level", "risk_score"],
        )

        # Build date → {high, medium, low} buckets
        from collections import defaultdict
        buckets = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})

        for alert in alerts:
            d = str(alert.posting_date)
            level = (alert.risk_level or "").lower()
            if "high" in level:
                buckets[d]["high"] += 1
            elif "medium" in level:
                buckets[d]["medium"] += 1
            elif "low" in level:
                buckets[d]["low"] += 1

        # Fill every calendar day so the chart has no gaps
        result = []
        current = getdate(from_date)
        while current <= to_date:
            ds = str(current)
            b  = buckets.get(ds, {"high": 0, "medium": 0, "low": 0})
            result.append({
                "date":   ds,
                "high":   b["high"],
                "medium": b["medium"],
                "low":    b["low"],
            })
            current = add_days(current, 1)

        return result

    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "FinGuard: get_risk_trend failed")
        frappe.throw(_("Failed to load risk trend: {0}").format(str(exc)))


@frappe.whitelist()
def get_top_alerts(company=None, limit=10):
    """
    Return top N unresolved alerts ordered by risk_score descending.
    """
    try:
        limit = int(limit)
        filters = [["status", "in", ["Open", "Under Investigation"]]]
        if company:
            filters.append(["company", "=", company])

        alerts = frappe.db.get_all(
            "Financial Anomaly Alert",
            filters=filters,
            fields=[
                "name", "title as alert_title", "risk_level", "risk_score",
                "party", "party_type", "amount as transaction_amount",
                "posting_date", "status", "source_doctype", "source_document as source_docname",
            ],
            order_by="risk_score desc",
            limit=limit,
        )

        return alerts

    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "FinGuard: get_top_alerts failed")
        frappe.throw(_("Failed to load top alerts: {0}").format(str(exc)))


@frappe.whitelist()
def get_rule_breakdown():
    """
    Return count of each triggered rule across all alerts.
    Returns list of {rule, count} suitable for a bar chart.
    """
    try:
        # triggered_rules is a JSON/text field containing comma-separated rule names
        alerts = frappe.db.get_all(
            "Financial Anomaly Alert",
            fields=["triggered_rules"],
            filters=[["triggered_rules", "!=", ""]],
        )

        from collections import Counter
        counter = Counter()

        for alert in alerts:
            rules_raw = alert.triggered_rules or ""
            # Support JSON list or comma-separated string
            if rules_raw.strip().startswith("["):
                import json
                try:
                    rules = json.loads(rules_raw)
                except Exception:
                    rules = [r.strip() for r in rules_raw.split(",") if r.strip()]
            else:
                rules = [r.strip() for r in rules_raw.split(",") if r.strip()]

            for rule in rules:
                if rule:
                    counter[rule] += 1

        result = [{"rule": rule, "count": count} for rule, count in counter.most_common(20)]
        return result

    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "FinGuard: get_rule_breakdown failed")
        frappe.throw(_("Failed to load rule breakdown: {0}").format(str(exc)))


@frappe.whitelist()
def get_party_risk_map(company=None, limit=20):
    """
    Return top parties by number of anomalies (for heat-map / table).
    Returns list of {party, party_type, alert_count, avg_risk_score, total_amount}.
    """
    try:
        limit = int(limit)
        filters = {}
        if company:
            filters["company"] = company

        alerts = frappe.db.get_all(
            "Financial Anomaly Alert",
            filters=filters,
            fields=["party", "party_type", "risk_score", "transaction_amount"],
        )

        from collections import defaultdict
        party_map = defaultdict(lambda: {"count": 0, "score_sum": 0.0, "amount_sum": 0.0, "party_type": ""})

        for alert in alerts:
            key = alert.party or "Unknown"
            party_map[key]["count"]      += 1
            party_map[key]["score_sum"]  += flt(alert.risk_score)
            party_map[key]["amount_sum"] += flt(alert.transaction_amount)
            if alert.party_type:
                party_map[key]["party_type"] = alert.party_type

        result = []
        for party, data in party_map.items():
            result.append({
                "party":          party,
                "party_type":     data["party_type"],
                "alert_count":    data["count"],
                "avg_risk_score": round(data["score_sum"] / data["count"], 2) if data["count"] else 0,
                "total_amount":   round(data["amount_sum"], 2),
            })

        result.sort(key=lambda x: x["alert_count"], reverse=True)
        return result[:limit]

    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "FinGuard: get_party_risk_map failed")
        frappe.throw(_("Failed to load party risk map: {0}").format(str(exc)))


@frappe.whitelist()
def run_manual_scan(company=None, from_date=None, to_date=None):
    """
    Trigger a manual full anomaly scan from the dashboard.
    Restricted to Accounts Manager role.
    """
    frappe.only_for("Accounts Manager")

    try:
        from finance_ai.scheduled_tasks.run_anomaly_scan import run_full_scan

        from_date, to_date = _date_defaults(from_date, to_date)
        result = run_full_scan(
            company=company,
            from_date=str(from_date),
            to_date=str(to_date),
        )
        frappe.msgprint(
            _("Manual scan completed. Alerts generated: {0}").format(result.get("alerts_created", 0)),
            title=_("FinGuard AI Scan"),
            indicator="green",
        )
        return result

    except ImportError:
        frappe.throw(_("Anomaly scan module not found. Please ensure scheduled_tasks are deployed."))
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "FinGuard: run_manual_scan failed")
        frappe.throw(_("Manual scan failed: {0}").format(str(exc)))
