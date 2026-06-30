from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from . import db
from .config import Settings
from .models import ApprovalDecision, Decision, Invoice, ProcessingResult, ValidationReport


def mock_payment(vendor, amount):
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}


def _append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def settle(inv: Invoice, validation: ValidationReport, approval: ApprovalDecision,
           settings: Settings) -> ProcessingResult:
    now = datetime.now(timezone.utc).isoformat()
    if approval.decision == Decision.APPROVE and (inv.amount is None or inv.amount <= 0):
        approval = approval.model_copy(deep=True)
        approval.decision = Decision.NEEDS_HUMAN_REVIEW
        approval.rationale = ("Payment blocked: approved invoice has no positive amount. "
                              + approval.rationale)
    if approval.decision == Decision.APPROVE and (validation.has_fail or approval.risk_score >= settings.fraud_reject):
        blocker = ("unresolved validation failures" if validation.has_fail
                   else f"fraud risk {approval.risk_score}/100")
        approval = approval.model_copy(deep=True)
        approval.decision = Decision.NEEDS_HUMAN_REVIEW
        approval.rationale = (f"Payment blocked: cannot disburse with {blocker}; routed to human review. "
                              + approval.rationale)
    result = ProcessingResult(invoice=inv, validation=validation, approval=approval)
    runs_dir = Path(settings.runs_dir)

    if approval.decision == Decision.APPROVE:
        payment_id = "PAY-" + uuid.uuid4().hex[:12].upper()
        claimed = db.claim_payment(
            invoice_number=inv.invoice_number, revision=inv.revision, total=inv.amount,
            payment_id=payment_id, created_at=now, db_path=settings.db_path)
        if not claimed:
            prior = db.find_paid(inv.invoice_number, settings.db_path)
            result.status = "SUPERSEDED"
            result.dedup_reason = (f"invoice {inv.invoice_number} was already paid "
                                   f"(payment_id {prior['payment_id'] if prior else 'unknown'}) - blocked to prevent double-pay")
            result.amount_at_risk = inv.amount if (inv.amount and inv.amount > 0) else Decimal("0")
            db.record_processing(
                invoice_number=inv.invoice_number, vendor=inv.vendor, amount=inv.amount,
                currency=inv.currency, decision="DUPLICATE_BLOCKED", reason=result.dedup_reason,
                payment_id=None, created_at=now, db_path=settings.db_path)
            return result

        pay = mock_payment(inv.vendor, inv.amount)
        result.payment = {**pay, "payment_id": payment_id, "paid_at": now,
                          "amount": str(inv.amount), "vendor": inv.vendor}
        result.status = "OK"
        result.amount_at_risk = Decimal("0")
        db.record_processing(
            invoice_number=inv.invoice_number, vendor=inv.vendor, amount=inv.amount,
            currency=inv.currency, decision="APPROVE", reason=approval.rationale,
            payment_id=payment_id, created_at=now, db_path=settings.db_path)
        _append_jsonl(runs_dir / "payments.jsonl", {
            "invoice_number": inv.invoice_number, "vendor": inv.vendor,
            "amount": str(inv.amount), "currency": inv.currency,
            "payment_id": payment_id, "paid_at": now})
    else:
        status = "REJECTED" if approval.decision == Decision.REJECT else "NEEDS_HUMAN_REVIEW"
        result.status = status
        result.amount_at_risk = inv.amount if (inv.amount and inv.amount > 0) else Decimal("0")
        rec = {
            "invoice_number": inv.invoice_number, "vendor": inv.vendor,
            "amount": str(inv.amount), "currency": inv.currency,
            "decision": approval.decision.value, "status": status,
            "risk_score": approval.risk_score, "rationale": approval.rationale,
            "reflection": approval.reflection,
            "issues": [i.model_dump(mode="json") for i in validation.issues],
            "logged_at": now,
        }
        _append_jsonl(runs_dir / "rejections.jsonl", rec)
        db.record_processing(
            invoice_number=inv.invoice_number, vendor=inv.vendor, amount=inv.amount,
            currency=inv.currency, decision=approval.decision.value,
            reason=approval.rationale, payment_id=None, created_at=now, db_path=settings.db_path)
        db.record_ledger(
            invoice_number=inv.invoice_number, revision=inv.revision, total=inv.amount,
            status=status, payment_id=None, created_at=now, db_path=settings.db_path)
    return result
