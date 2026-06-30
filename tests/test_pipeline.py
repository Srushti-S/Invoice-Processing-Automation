from decimal import Decimal

import pytest

from invoice_ai.approval import decide
from invoice_ai.ingestion import ingest
from invoice_ai.models import Decision
from invoice_ai.pipeline import run_batch, run_one
from invoice_ai.validation import aggregate_items, validate

DATA = "data/invoices"
CUSTOM = "data/custom_invoices"

EXPECTED = {
    "invoice_1001.txt": "OK",
    "invoice_1002.txt": "REJECTED",
    "invoice_1003.txt": "REJECTED",
    "invoice_1004.json": "OK",
    "invoice_1004_revised.json": "OK",
    "invoice_1005.json": "REJECTED",
    "invoice_1006.csv": "OK",
    "invoice_1007.csv": "REJECTED",
    "invoice_1008.txt": "REJECTED",
    "invoice_1009.json": "REJECTED",
    "invoice_1010.txt": "OK",
    "invoice_1011.txt": "OK",
    "invoice_1011.pdf": "OK",
    "invoice_1012.txt": "OK",
    "invoice_1012.pdf": "OK",
    "invoice_1013.json": "REJECTED",
    "invoice_1013.pdf": "REJECTED",
    "invoice_1014.xml": "OK",
    "invoice_1015.csv": "OK",
    "invoice_1016.json": "REJECTED",
}


@pytest.mark.parametrize("fname,expected", list(EXPECTED.items()))
def test_single_file_disposition(fname, expected, reasoner, settings):
    res = run_one(f"{DATA}/{fname}", reasoner, settings)
    assert res.status == expected, f"{fname}: got {res.status}, want {expected}"


def test_aggregation_1013(reasoner):
    agg = aggregate_items(ingest(f"{DATA}/invoice_1013.json", reasoner))
    assert agg == {"WidgetA": 22, "WidgetB": 18, "GadgetX": 9}


def test_aggregation_1010_passes(reasoner, settings):
    inv = ingest(f"{DATA}/invoice_1010.txt", reasoner)
    assert aggregate_items(inv)["WidgetA"] == 12
    assert validate(inv, settings.db_path).status == "PASS"


def test_arithmetic_overstatement_1013(reasoner, settings):
    rep = validate(ingest(f"{DATA}/invoice_1013.json", reasoner), settings.db_path)
    assert rep.total_delta == Decimal("50")
    assert any(i.code == "ARITHMETIC_MISMATCH" for i in rep.issues)


def test_arithmetic_understatement_1007(reasoner, settings):
    rep = validate(ingest(f"{DATA}/invoice_1007.csv", reasoner), settings.db_path)
    assert rep.total_delta == Decimal("-110")
    assert any(i.code == "ARITHMETIC_MISMATCH" for i in rep.issues)


def test_unknown_vs_out_of_stock(reasoner, settings):
    codes_1008 = {i.code for i in validate(ingest(f"{DATA}/invoice_1008.txt", reasoner), settings.db_path).issues}
    codes_1003 = {i.code for i in validate(ingest(f"{DATA}/invoice_1003.txt", reasoner), settings.db_path).issues}
    assert "UNKNOWN_ITEM" in codes_1008
    assert "OUT_OF_STOCK" in codes_1003


def test_negative_integrity_1009(reasoner, settings):
    rep = validate(ingest(f"{DATA}/invoice_1009.json", reasoner), settings.db_path)
    codes = {i.code for i in rep.issues}
    assert {"NEGATIVE_QUANTITY", "NEGATIVE_TOTAL", "MISSING_VENDOR"} <= codes
    assert rep.status == "FAIL"


def test_currency_preserved_1014(reasoner):
    assert ingest(f"{DATA}/invoice_1014.xml", reasoner).currency == "EUR"


def test_dedup_supersedes_original(reasoner, settings):
    results = run_batch(
        [f"{DATA}/invoice_1004.json", f"{DATA}/invoice_1004_revised.json"], reasoner, settings)
    revised = next(r for r in results if r.invoice.revision)
    original = next(r for r in results if not r.invoice.revision)
    assert revised.status == "OK"
    assert original.status == "SUPERSEDED"


def test_pdf_twin_not_double_paid(reasoner, settings):
    results = run_batch(
        [f"{DATA}/invoice_1011.txt", f"{DATA}/invoice_1011.pdf"], reasoner, settings)
    assert sum(1 for r in results if r.status == "OK") == 1
    assert sum(1 for r in results if r.status == "SUPERSEDED") == 1


def test_reflection_escalates_high_value(reasoner, settings):
    inv = ingest(f"{CUSTOM}/invoice_2001.json", reasoner)
    rep = validate(inv, settings.db_path)
    assert rep.status == "PASS"
    appr = decide(inv, rep, reasoner, settings)
    assert appr.decision == Decision.NEEDS_HUMAN_REVIEW
    assert appr.revised is True


def test_reflection_catches_threshold_gaming(reasoner, settings):
    inv = ingest(f"{CUSTOM}/invoice_2002.txt", reasoner)
    rep = validate(inv, settings.db_path)
    assert any(i.code == "ARITHMETIC_MISMATCH" for i in rep.issues)
    appr = decide(inv, rep, reasoner, settings)
    assert appr.decision == Decision.NEEDS_HUMAN_REVIEW
    assert appr.revised is True
