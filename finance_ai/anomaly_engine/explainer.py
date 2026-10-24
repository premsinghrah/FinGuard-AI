"""
FinGuard AI — Anomaly Explainer
================================
Converts raw scores + triggered rules into plain-English risk explanations
that a finance professional can act on immediately.

No Frappe dependency — pure Python.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from finance_ai.anomaly_engine.rule_engine import RULE_DESCRIPTIONS


# ---------------------------------------------------------------------------
# Indian number formatting
# ---------------------------------------------------------------------------

def format_amount(amount: float) -> str:
    """
    Format a number in Indian numbering (lakhs, crores) with ₹ symbol.

    Examples
    --------
    >>> format_amount(1500000)
    '₹15.00 L'
    >>> format_amount(25000000)
    '₹2.50 Cr'
    >>> format_amount(45000)
    '₹45,000'
    """
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return "₹0"

    abs_amount = abs(amount)
    sign = "-" if amount < 0 else ""

    if abs_amount >= 1_00_00_000:   # 1 Crore
        return f"{sign}₹{abs_amount / 1_00_00_000:.2f} Cr"
    elif abs_amount >= 1_00_000:    # 1 Lakh
        return f"{sign}₹{abs_amount / 1_00_000:.2f} L"
    else:
        # Indian comma formatting: xx,xx,xxx
        parts = f"{abs_amount:,.0f}".split(",")
        if len(parts) > 1:
            # Re-format to Indian style
            last   = parts[-1]
            rest   = ",".join(parts[:-1])
            indian = f"{rest},{last}"
        else:
            indian = parts[0]
        return f"{sign}₹{indian}"


# ---------------------------------------------------------------------------
# Explainer class
# ---------------------------------------------------------------------------

class AnomalyExplainer:
    """
    Generate human-readable risk explanations for financial anomaly alerts.

    The explanation includes:
    - ``risk_level``    : 'High Risk', 'Medium Risk', or 'Low Risk'
    - ``summary``       : 1–2 sentence plain-English overview
    - ``reasons``       : list of specific bullet-point reasons
    - ``recommendation``: what the investigator should do next
    """

    HIGH_THRESHOLD:   float = 0.75
    MEDIUM_THRESHOLD: float = 0.45

    def explain(
        self,
        transaction:    Dict[str, Any],
        composite_score: float,
        triggered_rules: List[str],
        is_duplicate:    bool,
        duplicate_reason: str = "",
    ) -> Dict[str, Any]:
        """
        Build a full explanation dict for a single transaction.

        Parameters
        ----------
        transaction:
            Raw transaction dict with fields: name, amount, party,
            posting_date, narration, source_doctype, etc.
        composite_score:
            Weighted composite risk score in [0, 1].
        triggered_rules:
            List of rule codes from RuleEngine.check().
        is_duplicate:
            Whether DuplicateDetector flagged this transaction.
        duplicate_reason:
            Human-readable duplicate reason string from DuplicateDetector.

        Returns
        -------
        dict with keys: risk_level, summary, reasons, recommendation
        """
        risk_level     = self._classify(composite_score)
        reasons        = self._build_reasons(triggered_rules, is_duplicate, duplicate_reason)
        summary        = self._build_summary(transaction, composite_score, triggered_rules, is_duplicate)
        recommendation = self._build_recommendation(risk_level, triggered_rules, is_duplicate)

        return {
            "risk_level":     risk_level,
            "summary":        summary,
            "reasons":        reasons,
            "recommendation": recommendation,
        }

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _classify(self, score: float) -> str:
        """Return risk level string from composite score."""
        if score >= self.HIGH_THRESHOLD:
            return "High Risk"
        if score >= self.MEDIUM_THRESHOLD:
            return "Medium Risk"
        return "Low Risk"

    def _build_reasons(
        self,
        rules: List[str],
        is_duplicate: bool,
        dup_reason: str,
    ) -> List[str]:
        """Build a bullet-point list of human-readable reasons."""
        reasons: List[str] = []
        for rule in rules:
            reasons.append(RULE_DESCRIPTIONS.get(rule, rule))
        if is_duplicate and dup_reason:
            reasons.append(f"Possible duplicate detected: {dup_reason}")
        elif is_duplicate:
            reasons.append("Transaction matches a near-duplicate entry in the system.")
        return reasons

    def _build_summary(
        self,
        t: Dict[str, Any],
        score: float,
        rules: List[str],
        is_duplicate: bool,
    ) -> str:
        """Build a 1–2 sentence plain-English summary."""
        doc_type = t.get("source_doctype", t.get("voucher_type", "Transaction"))
        doc_name = t.get("name", "")
        amount   = format_amount(float(t.get("amount", 0) or 0))
        party    = t.get("party", "Unknown Party")
        date_str = str(t.get("posting_date", ""))
        score_pct = round(score * 100, 1)

        # Lead sentence
        parts = [
            f"This {doc_type} ({doc_name}) for {amount} "
            f"by {party} on {date_str} has a composite risk score of {score_pct}%."
        ]

        # Supporting context
        context_parts = []
        if "OFF_HOURS_POSTING" in rules:
            hour = t.get("posting_hour", "")
            if hour != "":
                context_parts.append(f"posted at {int(hour):02d}:00")
        if "WEEKEND_POSTING" in rules:
            context_parts.append("posted on a weekend")
        if "ROUND_AMOUNT" in rules:
            context_parts.append("amount is a round number")
        if is_duplicate:
            context_parts.append("appears to be a near-duplicate of an existing transaction")
        if "LARGE_AMOUNT" in rules:
            context_parts.append("amount exceeds the large-transaction threshold")
        if "SELF_TRANSFER" in rules:
            context_parts.append("debit and credit parties appear identical")

        if context_parts:
            parts.append("Key flags: " + "; ".join(context_parts) + ".")

        return " ".join(parts)

    def _build_recommendation(
        self,
        risk_level: str,
        rules: List[str],
        is_duplicate: bool,
    ) -> str:
        """Return a specific recommended action for the investigator."""
        if risk_level == "High Risk":
            if is_duplicate:
                return (
                    "Immediately verify this transaction against the suspected duplicate. "
                    "If confirmed duplicate, reverse the newer entry and notify the AP/AR team. "
                    "Escalate to the Finance Controller if the amount exceeds approval limits."
                )
            if "SELF_TRANSFER" in rules:
                return (
                    "Investigate whether funds were transferred between related parties "
                    "without proper authorisation. Obtain supporting documentation and "
                    "approval sign-offs."
                )
            return (
                "This alert requires urgent review by an Accounts Manager. "
                "Verify the source document, obtain supporting vouchers, and confirm "
                "authorisation before the end of the business day."
            )

        if risk_level == "Medium Risk":
            if is_duplicate:
                return (
                    "Compare this transaction with the suspected duplicate. "
                    "If both are valid, add a clear narration to distinguish them. "
                    "If one is erroneous, raise a reversal journal entry."
                )
            return (
                "Review the transaction details and request supporting documentation. "
                "Confirm that the posting was authorised and correctly narrated. "
                "Resolve within 3 business days."
            )

        return (
            "Low priority. Add a note confirming the transaction is valid, "
            "or mark as False Positive if no further action is required."
        )

    def _rule_to_text(self, rule: str) -> str:
        """Map a rule code to its human-readable description."""
        return RULE_DESCRIPTIONS.get(rule, rule.replace("_", " ").title())
