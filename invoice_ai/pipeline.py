from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from . import db
from .config import Settings
from .graph import process_invoice
from .ingestion import ingest
from .llm import Reasoner
from .models import ProcessingResult
from .validation import dedup, validate

SUPPORTED = {".txt", ".json", ".csv", ".xml", ".pdf"}


def run_one(path: str, reasoner: Reasoner, settings: Settings) -> ProcessingResult:
    db.ensure_ledger(settings.db_path)
    try:
        return process_invoice(path, reasoner, settings)
    except Exception as e:
        inv = _safe_ingest(path, reasoner)
        return ProcessingResult(invoice=inv, status="ERROR", error=str(e))


def _safe_ingest(path, reasoner):
    try:
        return ingest(path, reasoner)
    except Exception:
        from .models import Invoice
        return Invoice(source_path=path, source_format=Path(path).suffix.lstrip("."))


def list_invoice_files(folder: str) -> list[str]:
    return sorted(str(p) for p in Path(folder).iterdir()
                  if p.is_file() and p.suffix.lower() in SUPPORTED)


def run_batch(paths: list[str], reasoner: Reasoner, settings: Settings) -> list[ProcessingResult]:
    db.ensure_ledger(settings.db_path)
    invoices = [_safe_ingest(p, reasoner) for p in paths]
    decisions = dedup(invoices)
    results: list[ProcessingResult | None] = [None] * len(invoices)

    primary_paid: dict[str, bool] = {}
    for i, inv in enumerate(invoices):
        if decisions[i]["primary"]:
            res = run_one_obj(inv, reasoner, settings)
            results[i] = res
            primary_paid[(inv.invoice_number or "").upper()] = res.status == "OK"

    for i, inv in enumerate(invoices):
        if not decisions[i]["primary"]:
            d = decisions[i]
            amt = inv.amount if (inv.amount and inv.amount > 0) else Decimal("0")
            if d.get("conflict"):
                status, risk = "NEEDS_HUMAN_REVIEW", amt
            else:
                paid = primary_paid.get((inv.invoice_number or "").upper(), False)
                status, risk = "SUPERSEDED", (amt if paid else Decimal("0"))
            results[i] = ProcessingResult(
                invoice=inv, validation=validate(inv, settings.db_path),
                status=status, dedup_reason=d["reason"], amount_at_risk=risk)
    return results


def run_one_obj(inv, reasoner: Reasoner, settings: Settings) -> ProcessingResult:
    try:
        return process_invoice(inv.source_path or "", reasoner, settings, invoice=inv)
    except Exception as e:
        return ProcessingResult(invoice=inv, status="ERROR", error=str(e))


def summarize(results: list[ProcessingResult]) -> dict:
    paid = [r for r in results if r.status == "OK"]
    rejected = [r for r in results if r.status == "REJECTED"]
    review = [r for r in results if r.status == "NEEDS_HUMAN_REVIEW"]
    superseded = [r for r in results if r.status == "SUPERSEDED"]
    errors = [r for r in results if r.status == "ERROR"]
    paid_total = sum((r.invoice.amount or Decimal("0")) for r in paid)
    at_risk = sum((r.amount_at_risk or Decimal("0"))
                  for r in rejected + review + superseded)
    return {
        "total": len(results), "paid": len(paid), "rejected": len(rejected),
        "review": len(review), "superseded": len(superseded), "errors": len(errors),
        "paid_total": paid_total, "amount_at_risk_flagged": at_risk,
    }
