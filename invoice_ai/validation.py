from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from . import db
from .models import Invoice, Severity, ValidationReport

TOLERANCE = Decimal("1.00")


def _revision_rank(rev: Optional[str]) -> int:
    if not rev:
        return 0
    m = re.search(r"\d+", str(rev))
    return int(m.group()) if m else 0


def _agg_key(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().casefold()


def aggregate_items(inv: Invoice) -> dict[str, int]:
    agg: dict[str, int] = {}
    display: dict[str, str] = {}
    for li in inv.items:
        k = _agg_key(li.item)
        if not k:
            continue
        agg[k] = agg.get(k, 0) + (li.quantity or 0)
        display.setdefault(k, li.item)
    return {display[k]: v for k, v in agg.items()}


def _content_sig(inv: Invoice):
    amt = inv.amount.quantize(Decimal("0.01")) if inv.amount is not None else None
    items = tuple(sorted((_agg_key(li.item), li.quantity or 0) for li in inv.items))
    return (str(amt), items)


def _line_sum(inv: Invoice) -> Optional[Decimal]:
    total = Decimal("0")
    seen = False
    for li in inv.items:
        if li.unit_price is not None:
            total += Decimal(li.quantity or 0) * li.unit_price
            seen = True
        elif li.line_total is not None:
            total += li.line_total
            seen = True
    return total if seen else None


def validate(inv: Invoice, db_path: str = db.DEFAULT_DB) -> ValidationReport:
    report = ValidationReport()
    agg = aggregate_items(inv)
    report.aggregated_items = agg

    for item, qty in agg.items():
        row = db.query_inventory(item, db_path)
        if not row["found"]:
            report.add("UNKNOWN_ITEM", f"{item!r} is not in the inventory catalog",
                       Severity.FAIL, item)
        elif row["stock"] == 0:
            report.add("OUT_OF_STOCK", f"{item!r} has zero stock (cannot fulfill {qty})",
                       Severity.FAIL, item)
        elif qty > row["stock"]:
            report.add("OVERSTOCK",
                       f"{item}: ordered {qty} exceeds stock {row['stock']}",
                       Severity.WARN, item)

    if not inv.items:
        report.add("NO_LINE_ITEMS", "no line items could be extracted", Severity.FAIL)
    for li in inv.items:
        if li.quantity is not None and li.quantity < 0:
            report.add("NEGATIVE_QUANTITY",
                       f"{li.item}: negative quantity {li.quantity}", Severity.FAIL, li.item)
    if not (inv.vendor and inv.vendor.strip()):
        report.add("MISSING_VENDOR", "vendor name is empty/missing", Severity.FAIL)
    if inv.amount is None:
        report.add("MISSING_TOTAL", "stated total is missing", Severity.WARN)
    elif inv.amount < 0:
        report.add("NEGATIVE_TOTAL", f"stated total is negative ({inv.amount})", Severity.FAIL)
    if inv.due_date is None:
        if inv.raw_due_date_text:
            report.add("UNPARSEABLE_DUE_DATE",
                       f"due date {inv.raw_due_date_text!r} is not a valid date",
                       Severity.WARN)
        else:
            report.add("MISSING_DUE_DATE", "due date is missing", Severity.WARN)

    unpriced = [li for li in inv.items
                if (li.quantity or 0) != 0 and li.unit_price is None and li.line_total is None]
    if unpriced:
        report.add("UNPRICED_LINE_ITEM",
                   f"{len(unpriced)} line item(s) have no price; totals can't be fully verified",
                   Severity.WARN, unpriced[0].item)

    line_sum = _line_sum(inv)
    base = inv.subtotal if inv.subtotal is not None else line_sum
    if (not unpriced and inv.subtotal is not None and line_sum is not None
            and abs(line_sum - inv.subtotal) > TOLERANCE):
        report.add("SUBTOTAL_MISMATCH",
                   f"line items sum to {line_sum} but stated subtotal is {inv.subtotal}",
                   Severity.FAIL)
    if base is not None and inv.amount is not None:
        tax = inv.tax_amount
        if tax is None and inv.tax_rate is not None:
            rate = inv.tax_rate
            if rate > 1:
                rate = rate / Decimal("100")
            tax = (base * rate).quantize(Decimal("0.01"))
        recomputed = base + (tax or Decimal("0")) + (inv.other_charges or Decimal("0"))
        delta = inv.amount - recomputed
        report.recomputed_total = recomputed
        report.stated_total = inv.amount
        report.total_delta = delta
        if abs(delta) > TOLERANCE:
            report.add("ARITHMETIC_MISMATCH",
                       f"stated total {inv.amount} != recomputed {recomputed} "
                       f"(delta {delta:+})", Severity.WARN)

    if any(i.severity == Severity.FAIL for i in report.issues):
        report.status = "FAIL"
    elif any(i.severity == Severity.WARN for i in report.issues):
        report.status = "WARN"
    else:
        report.status = "PASS"
    return report


def dedup(invoices: list[Invoice]) -> dict[int, dict]:
    source_rank = {"json": 3, "xml": 3, "csv": 3, "txt": 2, "pdf": 1}
    groups: dict[str, list[int]] = {}
    for i, inv in enumerate(invoices):
        key = (inv.invoice_number or f"__noid_{i}").upper()
        groups.setdefault(key, []).append(i)

    decisions: dict[int, dict] = {}
    for key, idxs in groups.items():
        if len(idxs) == 1:
            decisions[idxs[0]] = {"primary": True, "reason": "", "superseded_by": None,
                                  "conflict": False}
            continue
        def score(i: int):
            inv = invoices[i]
            return (_revision_rank(inv.revision),
                    source_rank.get(inv.source_format or "", 0))
        primary = max(idxs, key=score)
        for i in idxs:
            if i == primary:
                decisions[i] = {"primary": True, "reason": "", "superseded_by": None,
                                "conflict": False}
            else:
                inv = invoices[i]
                p = invoices[primary]
                if _revision_rank(p.revision) > _revision_rank(inv.revision):
                    reason = f"superseded by revision {p.revision or 'R?'} of {key}"
                    conflict = False
                elif _content_sig(p) == _content_sig(inv):
                    reason = f"duplicate of {key} (already counted from {p.source_format})"
                    conflict = False
                else:
                    reason = (f"CONFLICT: invoice number {key} appears twice with different "
                              "content (amount/items differ) - needs human review")
                    conflict = True
                decisions[i] = {"primary": False, "reason": reason,
                                "superseded_by": p.source_path, "conflict": conflict}
    return decisions
