import contextlib
import io
from decimal import Decimal

from invoice_ai.approval import decide
from invoice_ai.config import Settings
from invoice_ai.llm import MockReasoner
from invoice_ai.models import ApprovalDecision, Decision, Invoice, LineItem
from invoice_ai import db
from invoice_ai.payment import settle
from invoice_ai.validation import validate

R = MockReasoner()
W = lambda q, p="250": LineItem(item="WidgetA", quantity=q, unit_price=Decimal(p))


def _inv(**kw):
    return Invoice(vendor=kw.get("vendor", "Acme"), amount=kw.get("amount"),
                   currency=kw.get("currency", "USD"), due_date="2026-02-01",
                   invoice_number=kw.get("invoice_number", "INV-T"),
                   subtotal=kw.get("subtotal"), tax_amount=kw.get("tax_amount"),
                   items=kw.get("items", [W(2)]))


def _decide(inv, settings):
    return decide(inv, validate(inv, settings.db_path), R, settings)


def test_missing_amount_routes_to_review(settings):
    inv = _inv(amount=None, subtotal=Decimal("500"))
    assert _decide(inv, settings).decision == Decision.NEEDS_HUMAN_REVIEW


def test_arithmetic_mismatch_escalates_even_sub_threshold(settings):
    inv = _inv(amount=Decimal("1500"), subtotal=Decimal("1000"), tax_amount=Decimal("0"), items=[W(4)])
    a = _decide(inv, settings)
    assert a.decision == Decision.NEEDS_HUMAN_REVIEW
    assert a.revised is True


def test_tool_calls_are_recorded_on_the_decision(settings):
    class ToolReasoner(MockReasoner):
        def assess_fraud(self, facts, **ctx):
            return {"extra_signals": [], "extra_risk": 0,
                    "tool_log": ["check_inventory('WidgetA') -> stock=15, in_catalog=True"]}

    inv = _inv(amount=Decimal("500"), subtotal=Decimal("500"))
    a = decide(inv, validate(inv, settings.db_path), ToolReasoner(), settings)
    assert a.tool_calls == ["check_inventory('WidgetA') -> stock=15, in_catalog=True"]


def test_hallucinated_fraud_risk_is_clamped(settings):
    class Evil(MockReasoner):
        def assess_fraud(self, facts, **ctx):
            return {"extra_signals": ["HALLUCINATED"], "extra_risk": 1000}

    clean = _inv(amount=Decimal("500"), subtotal=Decimal("500"))
    a = decide(clean, validate(clean, settings.db_path), Evil(), settings)
    assert a.risk_score <= 40
    assert a.decision != Decision.REJECT
    assert a.decision == Decision.NEEDS_HUMAN_REVIEW


def test_reflection_text_consistent_with_decision(settings):
    inv = _inv(amount=Decimal("1500"), subtotal=Decimal("1000"), tax_amount=Decimal("0"), items=[W(4)])
    a = _decide(inv, settings)
    assert a.decision == Decision.NEEDS_HUMAN_REVIEW
    assert "approval is consistent" not in (a.reflection or "")


def test_small_non_usd_still_approves_with_note(settings):
    eur = _inv(amount=Decimal("4125"), currency="EUR", subtotal=Decimal("3750"),
               tax_amount=Decimal("375"),
               items=[LineItem(item="WidgetA", quantity=4, unit_price=Decimal("225")),
                      LineItem(item="WidgetB", quantity=6, unit_price=Decimal("475"))])
    a = _decide(eur, settings)
    assert a.decision == Decision.APPROVE
    assert "Non-USD" in a.rationale


def test_near_threshold_non_usd_is_scrutinized(settings):
    eur = _inv(amount=Decimal("9999"), currency="EUR", subtotal=Decimal("9999"),
               items=[LineItem(item="WidgetA", quantity=1, unit_price=Decimal("9999"))])
    assert _decide(eur, settings).decision == Decision.NEEDS_HUMAN_REVIEW


def test_payer_refuses_to_pay_none_amount(settings):
    inv = _inv(amount=None, subtotal=Decimal("500"))
    rep = validate(inv, settings.db_path)
    forced = ApprovalDecision(decision=Decision.APPROVE, rationale="forced")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = settle(inv, rep, forced, settings)
    assert res.status == "NEEDS_HUMAN_REVIEW"
    assert res.payment is None
    assert "Paid" not in buf.getvalue()


def test_cross_run_idempotency_blocks_double_pay(settings):
    inv = _inv(amount=Decimal("500"), subtotal=Decimal("500"), invoice_number="INV-IDEM")
    rep = validate(inv, settings.db_path)
    appr = decide(inv, rep, R, settings)
    assert appr.decision == Decision.APPROVE
    with contextlib.redirect_stdout(io.StringIO()):
        first = settle(inv, rep, appr, settings)
        second = settle(inv, rep, appr, settings)
    assert first.status == "OK" and first.payment is not None
    assert second.status == "SUPERSEDED" and second.payment is None
    assert "already paid" in (second.dedup_reason or "")


def test_payment_only_on_approve(settings):
    inv = _inv(amount=Decimal("500"), subtotal=Decimal("500"))
    rep = validate(inv, settings.db_path)
    for dec in (Decision.REJECT, Decision.NEEDS_HUMAN_REVIEW):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = settle(inv, rep, ApprovalDecision(decision=dec, rationale="x"), settings)
        assert res.payment is None and "Paid" not in buf.getvalue()


def test_settle_refuses_forced_approve_on_failed_or_fraud_invoice(settings):
    unfulfillable = _inv(amount=Decimal("500"), subtotal=Decimal("500"), invoice_number="INV-FORCE",
                         items=[LineItem(item="Mystery", quantity=2, unit_price=Decimal("250"))])
    rep = validate(unfulfillable, settings.db_path)
    assert rep.has_fail
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = settle(unfulfillable, rep, ApprovalDecision(decision=Decision.APPROVE, rationale="override"), settings)
    assert res.status == "NEEDS_HUMAN_REVIEW"
    assert res.payment is None and "Paid" not in buf.getvalue()

    clean = _inv(amount=Decimal("500"), subtotal=Decimal("500"), invoice_number="INV-FRAUD")
    crep = validate(clean, settings.db_path)
    with contextlib.redirect_stdout(io.StringIO()):
        res2 = settle(clean, crep, ApprovalDecision(decision=Decision.APPROVE, rationale="override", risk_score=80), settings)
    assert res2.status == "NEEDS_HUMAN_REVIEW"
    assert res2.payment is None


def test_concurrent_claim_grants_single_winner(settings):
    kw = dict(invoice_number="INV-RACE", revision=None, total=Decimal("500"),
              created_at="2026-01-01T00:00:00", db_path=settings.db_path)
    first = db.claim_payment(payment_id="PAY-A", **kw)
    second = db.claim_payment(payment_id="PAY-B", **kw)
    assert first is True and second is False
    held = db.find_paid("INV-RACE", settings.db_path)
    assert held and held["payment_id"] == "PAY-A"


def test_llm_reasoner_tools_build_and_degrade():
    from invoice_ai.llm import LLMReasoner
    reasoner = LLMReasoner("ollama")
    out = reasoner.assess_fraud({"vendor": "Acme", "amount": "100"})
    assert isinstance(out, dict)
    assert "extra_risk" in out and "tool_log" in out
