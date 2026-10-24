# Copyright (c) 2024, FinGuard AI
# License: MIT

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AnomalyModelLog(Document):
    """
    Read-only log of each anomaly scan run.
    Records are created and updated by the scanner module.
    """

    def before_insert(self):
        if not self.scan_start:
            self.scan_start = now_datetime()
        if not self.status:
            self.status = "Running"

    def mark_complete(self, transactions_scanned: int, alerts_created: int, alerts_updated: int) -> None:
        """Convenience method to finalise the log record."""
        self.scan_end             = now_datetime()
        self.status               = "Completed"
        self.transactions_scanned = transactions_scanned
        self.alerts_created       = alerts_created
        self.alerts_updated       = alerts_updated
        self.save(ignore_permissions=True)

    def mark_failed(self, error: str) -> None:
        """Mark the scan as failed with an error message."""
        self.scan_end  = now_datetime()
        self.status    = "Failed"
        self.error_log = error
        self.save(ignore_permissions=True)
