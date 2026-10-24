# Copyright (c) 2024, FinGuard AI and contributors
# For license information, please see license.txt

"""
FinGuard AI — Investigation API Endpoints
Provides detailed alert investigation capabilities.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days


# ---------------------------------------------------------------------------
# Key fields to pull from each supported source doctype
# ---------------------------------------------------------------------------

_SOURCE_FIELDS = {
    "GL Entry": [
        "name", "posting_date", "account", "debit", "credit",
        "party_type", "party", "against", "voucher_type",
        "voucher_no", "remarks", "company", "cost_center",
    ],
    "Journal Entry": [
        "name", "posting_date", "voucher_type", "total_debit",
        "total_credit", "remark", "company", "cheque_no",
        "cheque_date", "user_remark", "docstatus",
    ],
    "Payment Entry": [
        "name", "posting_date", "payment_type", "party_type",
        "party", "party_name", "paid_amount", "received_amount",
        "source_exchange_rate", "reference_no", "reference_date",
        "remarks", "company", "mode_of_payment", "docstatus",
    ],
    "Purchase Invoice": [
        "name", "posting_date", "supplier", "supplier_name",
        "grand_total", "outstanding_amount", "due_date",
        "bill_no", "bill_date", "company", "docstatus",
    ],
    "Sales Invoice": [
        "name", "posting_date", "customer", "customer_name",
        "grand_total", "outstanding_amount", "due_date",
        "company", "docstatus",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_alert_details(alert_name):
    """
    Return full alert document dict plus key fields from the linked source document.
    """
    if not alert_name:
        frappe.throw(_("Alert name is required."))

    alert = frappe.get_doc("Financial Anomaly Alert", alert_name)
    if not alert:
        frappe.throw(_("Alert {0} not found.").format(alert_name))

    result = alert.as_dict()

    # Append source document summary if available
    if alert.source_doctype and alert.source_docname:
        try:
            result["source_document_summary"] = get_source_document(
                alert.source_doctype, alert.source_docname
            )
        except Exception:
            result["source_document_summary"] = None

    # Decode triggered_rules if stored as JSON string
    if isinstance(result.get("triggered_rules"), str):
        import json
        try:
            result["triggered_rules_list"] = json.loads(result["triggered_rules"])
        except Exception:
            result["triggered_rules_list"] = [
                r.strip() for r in result["triggered_rules"].split(",") if r.strip()
            ]
    else:
        result["triggered_rules_list"] = result.get("triggered_rules") or []

    return result


@frappe.whitelist()
def get_source_document(doctype, docname):
    """
    Return key fields from a source GL/Journal/Payment/Invoice document.
    Falls back to a generic field set if doctype is unrecognised.
    """
    if not doctype or not docname:
        frappe.throw(_("Both doctype and docname are required."))

    # Security: only allow known financial doctypes
    allowed_doctypes = list(_SOURCE_FIELDS.keys()) + [
        "Expense Claim", "Salary Slip", "Stock Entry",
    ]
    if doctype not in allowed_doctypes:
        frappe.throw(_("Document type '{0}' is not supported for investigation.").format(doctype))

    if not frappe.db.exists(doctype, docname):
        frappe.throw(_("{0} '{1}' does not exist.").format(doctype, docname))

    fields = _SOURCE_FIELDS.get(doctype, ["name", "posting_date", "company"])

    doc_data = frappe.db.get_value(doctype, docname, fields, as_dict=True)
    if not doc_data:
        return {}

    doc_data["_doctype"] = doctype
    doc_data["_docname"] = docname
    doc_data["_link"]    = f"/app/{frappe.scrub(doctype)}/{docname}"

    return doc_data


@frappe.whitelist()
def update_alert_status(alert_name, status, notes=None):
    """
    Update the status (and optionally investigation notes) of an alert.
    Valid statuses: Open, Under Review, Resolved, False Positive, Escalated.
    """
    VALID_STATUSES = ("Open", "Under Review", "Resolved", "False Positive", "Escalated")

    if not alert_name:
        frappe.throw(_("Alert name is required."))

    if status not in VALID_STATUSES:
        frappe.throw(
            _("Invalid status '{0}'. Allowed: {1}").format(status, ", ".join(VALID_STATUSES))
        )

    if not frappe.db.exists("Financial Anomaly Alert", alert_name):
        frappe.throw(_("Alert '{0}' not found.").format(alert_name))

    update_dict = {"status": status}

    if notes:
        # Append timestamped note rather than replacing
        existing_notes = frappe.db.get_value("Financial Anomaly Alert", alert_name, "investigation_notes") or ""
        timestamp = frappe.utils.now()
        user = frappe.session.user
        appended = f"\n\n[{timestamp} — {user}]\n{notes}"
        update_dict["investigation_notes"] = existing_notes + appended

    if status in ("Resolved", "False Positive"):
        update_dict["resolution_date"] = frappe.utils.today()
        update_dict["resolved_by"]     = frappe.session.user

    frappe.db.set_value("Financial Anomaly Alert", alert_name, update_dict)
    frappe.db.commit()

    frappe.publish_realtime(
        "finguard_alert_updated",
        {"alert_name": alert_name, "status": status},
        user=frappe.session.user,
    )

    return {
        "success": True,
        "alert_name": alert_name,
        "new_status": status,
    }


@frappe.whitelist()
def get_similar_transactions(alert_name):
    """
    Return transactions (GL Entries) with a similar amount and/or party
    within a ±7 day window around the alert's posting date.
    Useful for pattern detection during investigation.
    """
    if not alert_name:
        frappe.throw(_("Alert name is required."))

    alert = frappe.db.get_value(
        "Financial Anomaly Alert",
        alert_name,
        ["posting_date", "party", "party_type", "amount", "company"],
        as_dict=True,
    )

    if not alert:
        frappe.throw(_("Alert '{0}' not found.").format(alert_name))

    posting_date = getdate(alert.posting_date)
    from_date    = add_days(posting_date, -7)
    to_date      = add_days(posting_date, 7)

    amount       = flt(alert.amount)
    lower_bound  = amount * 0.80  # within 20 %
    upper_bound  = amount * 1.20

    # Search GL Entries
    filters = [
        ["posting_date", "between", [str(from_date), str(to_date)]],
    ]
    if alert.company:
        filters.append(["company", "=", alert.company])

    if alert.party:
        filters.append(["party", "=", alert.party])
    elif amount > 0:
        # Fall back to amount-based search
        filters.append(["debit", "between", [lower_bound, upper_bound]])

    gl_entries = frappe.db.get_all(
        "GL Entry",
        filters=filters,
        fields=[
            "name", "posting_date", "account", "debit", "credit",
            "party_type", "party", "voucher_type", "voucher_no",
            "against", "remarks", "company",
        ],
        order_by="posting_date desc",
        limit=50,
    )

    # Also look up other FinGuard alerts for the same party
    alert_filters = []
    if alert.party:
        alert_filters.append(["party", "=", alert.party])
    alert_filters.append(["name", "!=", alert_name])
    alert_filters.append(["posting_date", "between", [str(from_date), str(to_date)]])

    related_alerts = []
    if alert_filters:
        related_alerts = frappe.db.get_all(
            "Financial Anomaly Alert",
            filters=alert_filters,
            fields=["name", "title as alert_title", "risk_level", "risk_score", "posting_date", "status"],
            order_by="risk_score desc",
            limit=10,
        )

    return {
        "gl_entries":     gl_entries,
        "related_alerts": related_alerts,
        "search_window":  {"from_date": str(from_date), "to_date": str(to_date)},
        "amount_range":   {"lower": lower_bound, "upper": upper_bound},
    }
