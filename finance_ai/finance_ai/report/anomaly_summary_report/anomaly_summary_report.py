# Copyright (c) 2024, FinGuard AI
# License: MIT

"""
FinGuard AI — Anomaly Summary Report
======================================
Lists all Financial Anomaly Alerts matching the given filters with
full detail columns and colour-coded risk indicators.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    """Return (columns, data) for the Anomaly Summary Report."""
    filters = filters or {}
    columns = _get_columns()
    data    = _get_data(filters)
    return columns, data


def _get_columns():
    return [
        {
            "fieldname": "name",
            "label":     _("Alert ID"),
            "fieldtype": "Link",
            "options":   "Financial Anomaly Alert",
            "width":     140,
        },
        {
            "fieldname": "source_doctype",
            "label":     _("Source Type"),
            "fieldtype": "Data",
            "width":     120,
        },
        {
            "fieldname": "source_document",
            "label":     _("Source Document"),
            "fieldtype": "Data",
            "width":     140,
        },
        {
            "fieldname": "risk_level",
            "label":     _("Risk Level"),
            "fieldtype": "Data",
            "width":     110,
        },
        {
            "fieldname": "risk_score_pct",
            "label":     _("Risk Score (%)"),
            "fieldtype": "Float",
            "precision": 1,
            "width":     120,
        },
        {
            "fieldname": "party",
            "label":     _("Party"),
            "fieldtype": "Data",
            "width":     140,
        },
        {
            "fieldname": "amount",
            "label":     _("Amount"),
            "fieldtype": "Currency",
            "width":     120,
        },
        {
            "fieldname": "posting_date",
            "label":     _("Posting Date"),
            "fieldtype": "Date",
            "width":     110,
        },
        {
            "fieldname": "status",
            "label":     _("Status"),
            "fieldtype": "Data",
            "width":     140,
        },
        {
            "fieldname": "triggered_rules",
            "label":     _("Triggered Rules"),
            "fieldtype": "Data",
            "width":     200,
        },
        {
            "fieldname": "is_duplicate",
            "label":     _("Duplicate?"),
            "fieldtype": "Check",
            "width":     80,
        },
        {
            "fieldname": "summary",
            "label":     _("Summary"),
            "fieldtype": "Data",
            "width":     300,
        },
    ]


def _get_data(filters):
    conditions = []
    values     = {}

    if filters.get("company"):
        conditions.append("company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("from_date"):
        conditions.append("posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("risk_level"):
        conditions.append("risk_level = %(risk_level)s")
        values["risk_level"] = filters["risk_level"]

    if filters.get("status"):
        conditions.append("status = %(status)s")
        values["status"] = filters["status"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    raw = frappe.db.sql(
        f"""
        SELECT
            name, source_doctype, source_document,
            risk_level, risk_score, party, amount,
            posting_date, status, triggered_rules,
            is_duplicate, summary
        FROM `tabFinancial Anomaly Alert`
        {where}
        ORDER BY risk_score DESC, posting_date DESC
        """,
        values,
        as_dict=True,
    )

    result = []
    for row in raw:
        # Convert score to percentage
        row["risk_score_pct"] = round(flt(row.get("risk_score", 0)) * 100, 1)

        # Colour the risk level cell using indicator map
        level = row.get("risk_level", "")
        if level == "High Risk":
            row["risk_level"] = f"<span style='color:#e02424;font-weight:700;'>● {level}</span>"
        elif level == "Medium Risk":
            row["risk_level"] = f"<span style='color:#d97706;font-weight:700;'>◆ {level}</span>"
        else:
            row["risk_level"] = f"<span style='color:#057a55;font-weight:600;'>▪ {level}</span>"

        # Trim long summaries
        summary = row.get("summary", "") or ""
        row["summary"] = summary[:120] + "…" if len(summary) > 120 else summary

        result.append(row)

    return result
