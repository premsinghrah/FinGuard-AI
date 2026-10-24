# Copyright (c) 2024, FinGuard AI
# License: MIT

"""
FinGuard AI — Risk Score Trend Report
=========================================
Returns daily average composite risk scores grouped by risk level,
suitable for rendering a trend chart in ERPNext's report builder.
"""

import frappe
from frappe import _
from frappe.utils import add_days, today, getdate


def execute(filters=None):
    filters = filters or {}
    columns = _get_columns()
    data    = _get_data(filters)
    return columns, data


def _get_columns():
    return [
        {"fieldname": "date",        "label": _("Date"),           "fieldtype": "Date",  "width": 110},
        {"fieldname": "high_count",  "label": _("High Risk"),       "fieldtype": "Int",   "width": 100},
        {"fieldname": "medium_count","label": _("Medium Risk"),     "fieldtype": "Int",   "width": 100},
        {"fieldname": "low_count",   "label": _("Low Risk"),        "fieldtype": "Int",   "width": 100},
        {"fieldname": "total",       "label": _("Total Alerts"),    "fieldtype": "Int",   "width": 110},
        {"fieldname": "avg_score",   "label": _("Avg Risk Score (%)"), "fieldtype": "Float","precision": 1, "width": 140},
    ]


def _get_data(filters):
    days      = int(filters.get("days", 30))
    to_date   = getdate(filters.get("to_date") or today())
    from_date = getdate(filters.get("from_date") or add_days(to_date, -days))

    company_filter = ""
    values = {"from_date": from_date, "to_date": to_date}

    if filters.get("company"):
        company_filter = "AND company = %(company)s"
        values["company"] = filters["company"]

    raw = frappe.db.sql(
        f"""
        SELECT
            posting_date                                           AS date,
            SUM(CASE WHEN risk_level='High Risk'   THEN 1 ELSE 0 END) AS high_count,
            SUM(CASE WHEN risk_level='Medium Risk' THEN 1 ELSE 0 END) AS medium_count,
            SUM(CASE WHEN risk_level='Low Risk'    THEN 1 ELSE 0 END) AS low_count,
            COUNT(*)                                               AS total,
            ROUND(AVG(risk_score) * 100, 1)                       AS avg_score
        FROM `tabFinancial Anomaly Alert`
        WHERE posting_date BETWEEN %(from_date)s AND %(to_date)s
          {company_filter}
        GROUP BY posting_date
        ORDER BY posting_date ASC
        """,
        values,
        as_dict=True,
    )

    return raw
