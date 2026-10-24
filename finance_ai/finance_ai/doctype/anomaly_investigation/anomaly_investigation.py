# Copyright (c) 2024, FinGuard AI
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AnomalyInvestigation(Document):
    """
    Investigation workflow record linked to a Financial Anomaly Alert.

    Lifecycle:
        Open → In Progress → Escalated → Closed (Confirmed Risk | False Positive)
    """

    def before_insert(self):
        if not self.opened_on:
            self.opened_on = now_datetime()
        if not self.investigator:
            self.investigator = frappe.session.user
        if not self.status:
            self.status = "Open"

    def on_update(self):
        if self.status and self.status.startswith("Closed") and not self.closed_on:
            self.closed_on = now_datetime()
            self.db_update()

    @frappe.whitelist()
    def close_investigation(self, decision: str, action_taken: str = "") -> dict:
        """
        Close the investigation with a final decision.

        Parameters
        ----------
        decision:
            'Confirmed Anomaly', 'False Positive', or 'Requires Escalation'.
        action_taken:
            Free-text description of actions taken.

        Returns
        -------
        dict with updated status and linked alert name.
        """
        valid_decisions = {"Confirmed Anomaly", "False Positive", "Requires Escalation", "Pending"}
        if decision not in valid_decisions:
            frappe.throw(_("Invalid decision: {0}").format(decision))

        self.decision    = decision
        self.action_taken = action_taken or self.action_taken
        self.closed_on   = now_datetime()

        if decision == "False Positive":
            self.status = "Closed — False Positive"
        elif decision == "Requires Escalation":
            self.status = "Escalated"
        else:
            self.status = "Closed — Confirmed Risk"

        self.save(ignore_permissions=False)

        # Update the linked alert
        if self.alert:
            try:
                alert = frappe.get_doc("Financial Anomaly Alert", self.alert)
                if decision == "False Positive":
                    alert.status = "False Positive"
                elif decision == "Confirmed Anomaly":
                    alert.status = "Resolved"
                alert.resolution_notes = action_taken or ""
                alert.save(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "FinGuard: close_investigation alert update failed")

        return {"status": self.status, "alert": self.alert}
