from decimal import Decimal

from invoice_ai.ingestion import ingest
from invoice_ai.llm import MockReasoner
from invoice_ai.models import Invoice, LineItem
from invoice_ai.normalize import fix_ocr_digits, parse_money
from invoice_ai.validation import _revision_rank, aggregate_items, dedup, validate

R = MockReasoner()


def test_ocr_fixer_leaves_alphabetic_words_alone():
    assert fix_ocr_digits("Volume") == "Volume"
    assert fix_ocr_digits("Bolt") == "Bolt"
    assert fix_ocr_digits("Tool") == "Tool"
    assert fix_ocr_digits("2O26") == "2026"
    assert fix_ocr_digits("$3,500.O0") == "$3,500.00"


def test_parse_money_accounting_negative_and_symbols():
    assert parse_money("(1,234.00)") == Decimal("-1234.00")
    assert parse_money("€2,500.00") == Decimal("2500.00")
    assert parse_money("£1,000.00") == Decimal("1000.00")
    assert parse_money("$1,500.00") == Decimal("1500.00")


def test_euro_text_invoice_parses_currency_and_items(tmp_path):
    f = tmp_path / "eur.txt"
    f.write_text(
        "INVOICE\nVendor: Euro Parts GmbH\nInvoice Number: INV-9001\n"
        "Date: 2026-02-01\nDue Date: 2026-03-01\nItems:\n"
        "  WidgetA   qty: 4   unit price: €250.00\nTotal Amount: €1,000.00\n")
    inv = ingest(str(f), R)
    assert inv.currency == "EUR"
    assert inv.amount == Decimal("1000.00")
    assert inv.items and inv.items[0].item == "WidgetA" and inv.items[0].unit_price == Decimal("250.00")


def test_bom_csv_still_parses(tmp_path):
    f = tmp_path / "bom.csv"
    f.write_text("﻿field,value\ninvoice_number,INV-9002\nvendor,BOM Co\n"
                 "item,WidgetA\nquantity,3\nunit_price,250.00\ntotal,750.00\n", encoding="utf-8")
    inv = ingest(str(f), R)
    assert inv.invoice_number == "INV-9002"
    assert inv.vendor == "BOM Co"
    assert [(li.item, li.quantity) for li in inv.items] == [("WidgetA", 3)]


def test_ocr_letters_in_invoice_number(tmp_path):
    f = tmp_path / "ocr.txt"
    f.write_text("INVOICE\nVendor: OCR Co\nINV NO: INV-1O13\nDue Date: 2026-02-01\n"
                 "Items:\n  WidgetA qty: 2 unit price: $250.00\nTotal Amount: $500.00\n")
    assert ingest(str(f), R).invoice_number == "INV-1013"


def test_issue_date_captured_for_text():
    assert ingest("data/invoices/invoice_1001.txt", R).date == "2026-01-15"


def _inv(items, **kw):
    return Invoice(vendor=kw.get("vendor", "Acme"), amount=kw.get("amount"),
                   subtotal=kw.get("subtotal"), tax_rate=kw.get("tax_rate"),
                   tax_amount=kw.get("tax_amount"), due_date="2026-02-01",
                   invoice_number=kw.get("invoice_number", "INV-TEST"),
                   revision=kw.get("revision"), items=items)


def test_case_insensitive_aggregation_catches_overstock(settings):
    inv = _inv([LineItem(item="WidgetA", quantity=10, unit_price=Decimal("250")),
                LineItem(item="widgeta", quantity=10, unit_price=Decimal("250"))])
    assert aggregate_items(inv) == {"WidgetA": 20}
    codes = {i.code for i in validate(inv, settings.db_path).issues}
    assert "OVERSTOCK" in codes


def test_tax_rate_as_percent_no_false_mismatch(settings):
    inv = _inv([LineItem(item="WidgetA", quantity=1, unit_price=Decimal("100"))],
               subtotal=Decimal("100"), tax_rate=Decimal("10"), amount=Decimal("110"))
    codes = {i.code for i in validate(inv, settings.db_path).issues}
    assert "ARITHMETIC_MISMATCH" not in codes


def test_unpriced_line_item_flagged_not_masked(settings):
    inv = _inv([LineItem(item="WidgetA", quantity=2, unit_price=None, line_total=None)],
               subtotal=Decimal("500"), amount=Decimal("500"))
    codes = {i.code for i in validate(inv, settings.db_path).issues}
    assert "UNPRICED_LINE_ITEM" in codes
    assert "SUBTOTAL_MISMATCH" not in codes


def test_revision_rank():
    assert _revision_rank(None) == 0
    assert _revision_rank("R1") == 1
    assert _revision_rank("Rev 2") == 2
    assert _revision_rank("draft") == 0
    assert _revision_rank("R0") == 0


def test_dedup_flags_same_number_different_content():
    a = _inv([LineItem(item="WidgetA", quantity=1, unit_price=Decimal("250"))],
             amount=Decimal("250"), invoice_number="INV-7000")
    b = _inv([LineItem(item="WidgetB", quantity=5, unit_price=Decimal("500"))],
             amount=Decimal("2500"), invoice_number="INV-7000")
    decisions = dedup([a, b])
    assert any(d.get("conflict") for d in decisions.values())


def test_dedup_identical_twins_not_conflict():
    items = [LineItem(item="WidgetA", quantity=1, unit_price=Decimal("250"))]
    a = _inv(list(items), amount=Decimal("250"), invoice_number="INV-7001")
    a.source_format = "txt"
    b = _inv(list(items), amount=Decimal("250"), invoice_number="INV-7001")
    b.source_format = "pdf"
    decisions = dedup([a, b])
    assert not any(d.get("conflict") for d in decisions.values())
