from __future__ import annotations

import re
from decimal import Decimal

from .config import Settings
from .llm import Reasoner
from .models import ApprovalDecision, Decision, Invoice, ValidationReport

_FRAUD_VENDOR = re.compile(r"(?i)\b(fraud|fraudster|scam|fake|phish)\b")
_URGENCY = re.compile(
    r"(?i)(urgent|immediately|asap|wire\s*transfer|act now|penalt|final notice|"
    r"overdue|pay now|right away)")


def fraud_assessment(inv: Invoice, validation: ValidationReport) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    codes = {i.code for i in validation.issues}

    if inv.vendor and _FRAUD_VENDOR.search(inv.vendor):
        score += 50
        signals.append(f"vendor name {inv.vendor!r} contains a fraud red-flag word")
    if "OUT_OF_STOCK" in codes:
        score += 25
        signals.append("orders an item with zero inventory (classic shell-item fraud)")
    blob = " ".join(filter(None, [inv.notes, inv.vendor, inv.raw_due_date_text]))
    if _URGENCY.search(blob or ""):
        score += 20
        signals.append("uses urgency / wire-transfer pressure language")
    if "UNPARSEABLE_DUE_DATE" in codes:
        score += 15
        signals.append("due date is relative/unparseable (e.g. 'yesterday')")
    if inv.amount is not None and inv.amount >= 50000 and inv.amount % 1000 == 0:
        score += 10
        signals.append("large round-number total (whale pattern)")
    if "ARITHMETIC_MISMATCH" in codes:
        score += 10
        signals.append("stated total does not reconcile with line items")
    if codes & {"NEGATIVE_QUANTITY", "NEGATIVE_TOTAL", "SUBTOTAL_MISMATCH"}:
        score += 15
        signals.append("contains negative or internally inconsistent amounts")
    return min(score, 100), signals


def _facts(inv: Invoice, validation: ValidationReport, signals: list[str], high: bool) -> dict:
    return {
        "invoice_number": inv.invoice_number,
        "vendor": inv.vendor,
        "amount": str(inv.amount),
        "currency": inv.currency,
        "high_scrutiny": high,
        "validation_status": validation.status,
        "issue_summary": "; ".join(f"{i.code}: {i.detail}" for i in validation.issues) or "none",
        "fraud_signals": signals,
        "aggregated_items": validation.aggregated_items,
    }


def baseline(inv: Invoice, validation: ValidationReport, reasoner: Reasoner,
             settings: Settings) -> ApprovalDecision:
    score, signals = fraud_assessment(inv, validation)
    threshold = settings.scrutiny_threshold
    non_usd = bool(inv.currency and inv.currency.upper() != "USD")
    eff_threshold = threshold * Decimal("0.5") if non_usd else threshold
    high = inv.amount is not None and inv.amount > eff_threshold
    facts = _facts(inv, validation, signals, high)

    adv = reasoner.assess_fraud(facts, inv=inv, validation=validation, db_path=settings.db_path)
    try:
        extra = int(adv.get("extra_risk", 0) or 0)
    except (TypeError, ValueError):
        extra = 0
    score = min(100, score + max(0, min(40, extra)))
    for s in adv.get("extra_signals", []):
        if s not in signals:
            signals.append(s)

    codes = {i.code for i in validation.issues}
    overstock = "OVERSTOCK" in codes

    if validation.has_fail:
        decision = Decision.REJECT
    elif score >= settings.fraud_reject:
        decision = Decision.REJECT
    elif overstock and high:
        decision = Decision.REJECT
    elif overstock:
        decision = Decision.NEEDS_HUMAN_REVIEW
    elif inv.amount is None:
        decision = Decision.NEEDS_HUMAN_REVIEW
    else:
        decision = Decision.APPROVE

    rationale = reasoner.write_vp_memo({**facts, "fraud_score": score}, decision.value)
    if non_usd:
        rationale += (f" (Non-USD invoice in {inv.currency}; the {threshold} scrutiny "
                      "threshold is USD and not FX-converted - verify if near the limit.)")
    return ApprovalDecision(decision=decision, rationale=rationale, risk_score=score,
                            fraud_signals=signals, high_scrutiny=high,
                            tool_calls=adv.get("tool_log", []))


def reflect_step(inv: Invoice, validation: ValidationReport, approval: ApprovalDecision,
                 reasoner: Reasoner, settings: Settings) -> ApprovalDecision:
    if not settings.reflection:
        return approval
    facts = _facts(inv, validation, approval.fraud_signals, approval.high_scrutiny)
    facts["fraud_score"] = approval.risk_score
    new = approval.model_copy(deep=True)
    escalation = _reflect_escalate(
        inv, validation, approval.risk_score, approval.high_scrutiny, approval.decision, settings)
    if escalation:
        new.decision = Decision.NEEDS_HUMAN_REVIEW
        new.revised = True
        new.rationale = reasoner.write_vp_memo(facts, new.decision.value)
    reflection = reasoner.write_reflection(facts, new.decision.value)
    if escalation:
        reflection += f"  Escalation trigger: {escalation}"
    new.reflection = ((approval.reflection + " | ") if approval.reflection else "") + reflection
    return new


def decide(inv: Invoice, validation: ValidationReport, reasoner: Reasoner,
           settings: Settings) -> ApprovalDecision:
    return reflect_step(inv, validation, baseline(inv, validation, reasoner, settings),
                        reasoner, settings)


def _reflect_escalate(inv: Invoice, validation: ValidationReport, score: int,
                      high: bool, decision: Decision, settings: Settings) -> str | None:
    if decision != Decision.APPROVE:
        return None
    codes = {i.code for i in validation.issues}
    if high:
        return (f"amount {inv.amount} exceeds the {settings.scrutiny_threshold} scrutiny "
                "threshold; policy requires a human sign-off")
    if settings.fraud_review <= score < settings.fraud_reject:
        return f"elevated fraud risk score ({score}) warrants a second look"
    if "ARITHMETIC_MISMATCH" in codes:
        delta = validation.total_delta
        d = f" (delta {delta:+})" if delta is not None else ""
        return f"stated total does not reconcile with line items{d}; do not pay until corrected"
    return None
