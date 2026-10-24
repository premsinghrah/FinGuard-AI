"""
Financial Anomaly Alert DocType controller.

Manages anomaly alerts raised by the FinGuard AI scan engine.
Provides lifecycle management including escalation to investigations
and resolution tracking.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class FinancialAnomalyAlert(Document):
    # ------------------------------------------------------------------ #
    #  Frappe lifecycle hooks                                              #
    # ------------------------------------------------------------------ #

    def before_insert(self):
        """Set computed fields before the record is first persisted."""
        self.set_title()

    def validate(self):
        """Run all validation checks on save/submit."""
        self.set_title()
        self.validate_scores()

    def on_update(self):
        """Auto-stamp resolution metadata when status transitions to Resolved."""
        if self.status == "Resolved" and not self.resolved_on:
            self.resolved_on = now_datetime()
            self.resolved_by = frappe.session.user
            # Use db_update to avoid recursion through validate/on_update
            self.db_update()

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def set_title(self):
        """
        Build a human-readable title from source document and risk level.
        Example: "JE-2024-00123 — High Risk"
        """
        source = self.source_document or "Unknown"
        risk = self.risk_level or "Unscored"
        self.title = f"{source} \u2014 {risk}"

    def validate_scores(self):
        """
        Ensure all score fields are within the valid [0.0, 1.0] range.
        Raises a frappe.ValidationError if any field is out of range.
        """
        score_fields = ["risk_score", "ml_score", "rule_score", "duplicate_score"]
        for field in score_fields:
            val = getattr(self, field, None)
            if val is not None and not (0.0 <= float(val) <= 1.0):
                frappe.throw(
                    _("{field} must be between 0 and 1, got {val}").format(
                        field=frappe.bold(field), val=val
                    ),
                    title=_("Invalid Score"),
                )

    # ------------------------------------------------------------------ #
    #  Whitelisted API methods                                             #
    # ------------------------------------------------------------------ #

    @frappe.whitelist()
    def mark_false_positive(self):
        """
        Mark this alert as a False Positive.
        Can be called from client-side buttons or REST API.

        Returns:
            dict: Confirmation message.
        """
        self.status = "False Positive"
        self.save(ignore_permissions=False)
        frappe.msgprint(_("Alert marked as False Positive."), alert=True)
        return {"message": "Marked as False Positive"}

    @frappe.whitelist()
    def escalate(self):
        """
        Escalate this alert to 'Under Investigation' and create a linked
        Anomaly Investigation document if one does not already exist.

        Returns:
            dict: Name of the created/existing investigation, or a message.
        """
        self.status = "Under Investigation"
        self.save(ignore_permissions=False)

        # Avoid duplicate investigations for the same alert
        existing = frappe.db.exists("Anomaly Investigation", {"alert": self.name})
        if existing:
            return {"message": "Investigation already exists", "investigation": existing}

        inv = frappe.new_doc("Anomaly Investigation")
        inv.alert = self.name
        inv.risk_level = self.risk_level
        inv.source_doctype = self.source_doctype
        inv.source_document = self.source_document
        inv.company = self.company
        inv.insert(ignore_permissions=True)

        frappe.msgprint(
            _("Investigation {0} created.").format(frappe.bold(inv.name)), alert=True
        )
        return {"investigation": inv.name}
