#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from invoice_ai import db
from invoice_ai.config import Settings
from invoice_ai.llm import get_reasoner
from invoice_ai.models import ProcessingResult
from invoice_ai.pipeline import (list_invoice_files, run_batch, run_one, summarize)

load_dotenv()

_DECISION_STYLE = {
    "OK": "bold green", "REJECTED": "bold red", "NEEDS_HUMAN_REVIEW": "bold yellow",
    "SUPERSEDED": "dim", "ERROR": "bold magenta",
}
_DECISION_LABEL = {
    "OK": "PAID", "REJECTED": "REJECTED", "NEEDS_HUMAN_REVIEW": "REVIEW",
    "SUPERSEDED": "SUPERSEDED", "ERROR": "ERROR",
}


def result_to_dict(res: ProcessingResult) -> dict:
    return res.model_dump(mode="json")


def _write_artifacts(results: list[ProcessingResult], out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for r in results:
        num = r.invoice.invoice_number or Path(r.invoice.source_path or "unknown").stem
        fmt = r.invoice.source_format or "x"
        (out / f"{num}_{fmt}.json").write_text(json.dumps(result_to_dict(r), indent=2))


def render_single(res: ProcessingResult, console) -> None:
    from rich.panel import Panel
    from rich.table import Table

    inv = res.invoice
    head = Table.grid(padding=(0, 2))
    head.add_row("Invoice", f"[bold]{inv.invoice_number or '-'}[/]")
    head.add_row("Vendor", str(inv.vendor or "-"))
    head.add_row("Amount", f"{inv.currency} {inv.amount if inv.amount is not None else '-'}")
    head.add_row("Due", str(inv.due_date or inv.raw_due_date_text or "-"))
    head.add_row("Source", f"{inv.source_format} (via {inv.extraction_method})")
    console.print(Panel(head, title="① Ingestion", border_style="cyan"))

    if inv.items:
        t = Table(show_header=True, header_style="bold")
        t.add_column("Item"); t.add_column("Qty", justify="right")
        t.add_column("Unit", justify="right"); t.add_column("Note")
        for li in inv.items:
            t.add_row(li.item, str(li.quantity),
                      f"{li.unit_price}" if li.unit_price is not None else "-", li.note or "")
        console.print(t)
    if inv.extraction_warnings:
        console.print(f"[yellow]extraction warnings:[/] {', '.join(inv.extraction_warnings)}")

    if res.validation:
        v = res.validation
        vt = Table(show_header=True, header_style="bold")
        vt.add_column("Severity"); vt.add_column("Code"); vt.add_column("Detail")
        for i in v.issues:
            sty = {"FAIL": "red", "WARN": "yellow", "INFO": "blue"}.get(i.severity.value, "white")
            vt.add_row(f"[{sty}]{i.severity.value}[/]", i.code, i.detail)
        body = vt if v.issues else "[green]no issues[/]"
        agg = ", ".join(f"{k}:{v2}" for k, v2 in v.aggregated_items.items())
        console.print(Panel(body, title=f"② Validation - {v.status}  (aggregated: {agg})",
                            border_style="cyan"))

    if res.approval:
        a = res.approval
        ap = Table.grid(padding=(0, 2))
        ap.add_row("Decision", f"[bold]{a.decision.value}[/]")
        ap.add_row("Risk score", str(a.risk_score))
        ap.add_row("High scrutiny", "yes" if a.high_scrutiny else "no")
        if a.tool_calls:
            ap.add_row("Tool calls", "\n".join(f"• {t}" for t in a.tool_calls))
        if a.fraud_signals:
            ap.add_row("Fraud signals", "\n".join(f"• {s}" for s in a.fraud_signals))
        ap.add_row("Rationale", a.rationale)
        if a.reflection:
            ap.add_row("Reflection", f"[italic]{a.reflection}[/]" + (" [bold yellow](decision revised)[/]" if a.revised else ""))
        console.print(Panel(ap, title="③ Approval (with reflection loop)", border_style="cyan"))

    style = _DECISION_STYLE.get(res.status, "white")
    final = _final_line(res)
    console.print(Panel(final, title="④ Payment / Outcome", border_style=style.split()[-1]))


def _final_line(res: ProcessingResult) -> str:
    if res.status == "OK":
        return f"[bold green]PAID[/] {res.invoice.currency} {res.invoice.amount} to {res.invoice.vendor}  (payment_id {res.payment['payment_id']})"
    if res.status == "REJECTED":
        return f"[bold red]REJECTED[/] - logged. ${res.amount_at_risk} kept from an erroneous payout."
    if res.status == "NEEDS_HUMAN_REVIEW":
        return f"[bold yellow]HELD FOR REVIEW[/] - {res.invoice.currency} {res.invoice.amount} pending human sign-off."
    if res.status == "SUPERSEDED":
        return f"[dim]SUPERSEDED[/] - {res.dedup_reason}. Double-pay of ${res.amount_at_risk} avoided."
    return f"[bold magenta]ERROR[/] - {res.error}"


def render_batch(results: list[ProcessingResult], console) -> None:
    from rich.table import Table

    t = Table(title="Invoice Processing - Batch Results", show_header=True, header_style="bold")
    t.add_column("Invoice"); t.add_column("Vendor", max_width=24); t.add_column("Amount", justify="right")
    t.add_column("Issues"); t.add_column("Decision"); t.add_column("$ at risk", justify="right")
    for r in results:
        inv = r.invoice
        issues = ",".join(sorted({i.code for i in (r.validation.issues if r.validation else [])})) or "-"
        style = _DECISION_STYLE.get(r.status, "white")
        label = _DECISION_LABEL.get(r.status, r.status)
        amt = f"{inv.currency} {inv.amount}" if inv.amount is not None else "-"
        risk = f"${r.amount_at_risk}" if r.amount_at_risk else "-"
        t.add_row(inv.invoice_number or "-", str(inv.vendor or "-"), amt,
                  issues, f"[{style}]{label}[/]", risk)
    console.print(t)

    s = summarize(results)
    console.print(
        f"\n[bold]{s['total']}[/] processed  |  "
        f"[green]{s['paid']} paid[/] (${s['paid_total']})  |  "
        f"[red]{s['rejected']} rejected[/]  |  "
        f"[yellow]{s['review']} review[/]  |  "
        f"[dim]{s['superseded']} superseded[/]  |  "
        f"[bold]${s['amount_at_risk_flagged']}[/] flagged away from erroneous payout")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Galatiq multi-agent invoice processor")
    ap.add_argument("--invoice_path", help="process a single invoice file")
    ap.add_argument("--batch", help="process every invoice in a folder")
    ap.add_argument("--provider", help="llm provider: mock|groq|grok|ollama|openai")
    ap.add_argument("--mock-llm", action="store_true", help="force the offline mock reasoner")
    ap.add_argument("--db", default="inventory.db", help="inventory SQLite path")
    ap.add_argument("--threshold", type=str, help="approval scrutiny threshold (USD)")
    ap.add_argument("--out", default="runs", help="artifacts output dir")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of rich output")
    args = ap.parse_args(argv)

    if not args.invoice_path and not args.batch:
        ap.error("provide --invoice_path=<file> or --batch <folder>")

    if not Path(args.db).exists():
        from setup_db import seed_inventory
        seed_inventory(args.db)

    settings = Settings(db_path=args.db, runs_dir=args.out)
    if args.threshold:
        settings.scrutiny_threshold = Decimal(args.threshold)
    provider = "mock" if args.mock_llm else args.provider
    reasoner = get_reasoner(provider, verbose=not args.json)

    from rich.console import Console
    console = Console()

    quiet = contextlib.redirect_stdout(io.StringIO()) if args.json else contextlib.nullcontext()

    if args.invoice_path:
        with quiet:
            res = run_one(args.invoice_path, reasoner, settings)
        _write_artifacts([res], args.out)
        if args.json:
            print(json.dumps(result_to_dict(res), indent=2))
        else:
            console.rule(f"[bold]{Path(args.invoice_path).name}[/]  ·  reasoner={reasoner.name}")
            render_single(res, console)
        return 0 if res.status != "ERROR" else 1

    paths = list_invoice_files(args.batch)
    with quiet:
        results = run_batch(paths, reasoner, settings)
    _write_artifacts(results, args.out)
    if args.json:
        print(json.dumps({"results": [result_to_dict(r) for r in results],
                          "summary": {k: str(v) for k, v in summarize(results).items()}}, indent=2))
    else:
        console.rule(f"[bold]Batch: {args.batch}[/]  ·  reasoner={reasoner.name}")
        render_batch(results, console)
    return 0


if __name__ == "__main__":
    sys.exit(main())
