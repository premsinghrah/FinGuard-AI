"""
Unit tests for the Financial Anomaly Alert DocType.
"""

import frappe
import unittest
from frappe.utils import flt


class TestFinancialAnomalyAlert(unittest.TestCase):
    """Test suite for FinancialAnomalyAlert DocType."""

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _make_alert(self, **kwargs):
        """Factory helper — creates and inserts a minimal valid alert."""
        defaults = {
            "doctype": "Financial Anomaly Alert",
            "risk_level": "High Risk",
            "risk_score": 0.92,
            "source_doctype": "Journal Entry",
            "source_document": "JE-TEST-00001",
            "company": frappe.defaults.get_global_default("company"),
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        return doc

    def tearDown(self):
        """Roll back any uncommitted changes after each test."""
        frappe.db.rollback()

    # ------------------------------------------------------------------ #
    #  Test: title auto-generation                                         #
    # ------------------------------------------------------------------ #

    def test_title_is_set_on_insert(self):
        """Title should be auto-generated as '<source_document> — <risk_level>'."""
        doc = self._make_alert(
            source_document="JE-2024-00123",
            risk_level="High Risk",
            risk_score=0.90,
        )
        expected = "JE-2024-00123 \u2014 High Risk"
        self.assertEqual(
            doc.title,
            expected,
            f"Expected title '{expected}', got '{doc.title}'",
        )

    # ------------------------------------------------------------------ #
    #  Test: score validation                                              #
    # ------------------------------------------------------------------ #

    def test_invalid_score_raises_error(self):
        """A risk_score outside [0, 1] must raise a ValidationError."""
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._make_alert(risk_score=1.5)

    def test_valid_boundary_scores_accepted(self):
        """Scores of exactly 0.0 and 1.0 should be accepted without error."""
        doc_zero = self._make_alert(risk_score=0.0, risk_level="Low Risk")
        self.assertAlmostEqual(flt(doc_zero.risk_score), 0.0)

        doc_one = self._make_alert(risk_score=1.0, risk_level="High Risk")
        self.assertAlmostEqual(flt(doc_one.risk_score), 1.0)
