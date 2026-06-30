from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from .normalize import extract_from_text, parse_money
from .models import Decision

PROVIDERS = {
    "grok":     {"base_url": "https://api.x.ai/v1", "key": "XAI_API_KEY",
                 "model": "XAI_MODEL", "default_model": "grok-3"},
    "groq":     {"base_url": "https://api.groq.com/openai/v1", "key": "GROQ_API_KEY",
                 "model": "GROQ_MODEL", "default_model": "llama-3.3-70b-versatile"},
    "gemini":   {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                 "key": "GEMINI_API_KEY", "model": "GEMINI_MODEL", "default_model": "gemini-2.0-flash"},
    "cerebras": {"base_url": "https://api.cerebras.ai/v1", "key": "CEREBRAS_API_KEY",
                 "model": "CEREBRAS_MODEL", "default_model": "llama-3.3-70b"},
    "mistral":  {"base_url": "https://api.mistral.ai/v1", "key": "MISTRAL_API_KEY",
                 "model": "MISTRAL_MODEL", "default_model": "mistral-small-latest"},
    "ollama":   {"base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                 "key": None, "model": "OLLAMA_MODEL", "default_model": "qwen2.5"},
}


class Reasoner(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, text: str, fmt: str) -> dict:
        ...

    @abstractmethod
    def assess_fraud(self, facts: dict, **ctx) -> dict:
        ...

    @abstractmethod
    def write_vp_memo(self, facts: dict, decision: str) -> str:
        ...

    @abstractmethod
    def write_reflection(self, facts: dict, decision: str) -> str:
        ...


class MockReasoner(Reasoner):
    name = "mock"

    def extract(self, text: str, fmt: str) -> dict:
        data = extract_from_text(text)
        data["extraction_method"] = "heuristic"
        return data

    def assess_fraud(self, facts: dict, **ctx) -> dict:
        return {"extra_signals": [], "extra_risk": 0, "tool_log": []}

    def write_vp_memo(self, facts: dict, decision: str) -> str:
        v = facts.get("vendor") or "the vendor"
        amt = facts.get("amount")
        issues = facts.get("issue_summary") or "no blocking issues"
        if decision == Decision.APPROVE.value:
            return (f"Approved payment to {v} for {facts.get('currency','USD')} {amt}. "
                    f"Validation clean ({issues}); amount within delegated authority.")
        if decision == Decision.REJECT.value:
            return (f"Rejected invoice from {v}. Blocking problems: {issues}. "
                    f"Do not release {facts.get('currency','USD')} {amt} until resolved.")
        return (f"Holding invoice from {v} for human review: {issues}. "
                f"Amount {facts.get('currency','USD')} {amt} warrants a second set of eyes.")

    def write_reflection(self, facts: dict, decision: str) -> str:
        score = facts.get("fraud_score", 0)
        issues = facts.get("issue_summary", "none")
        base = (f"Reflection: re-examined the {decision} call against risk score "
                f"{score} and validation findings ({issues}).")
        if decision == Decision.REJECT.value:
            return base + " Findings corroborate the rejection; funds withheld."
        if decision == Decision.APPROVE.value:
            return base + " No blocking issues or material fraud signals; approval is consistent."
        return base + " Residual ambiguity - routing to a human for adjudication."


class LLMReasoner(Reasoner):

    def __init__(self, provider: str):
        from langchain_openai import ChatOpenAI
        cfg = PROVIDERS[provider]
        self.name = provider
        self._mock = MockReasoner()
        api_key = os.environ.get(cfg["key"]) if cfg["key"] else "ollama"
        model = os.environ.get(cfg["model"], cfg["default_model"])
        self.model_name = model
        self.llm = ChatOpenAI(
            model=model, base_url=cfg["base_url"], api_key=api_key, temperature=0.0,
        )

    def extract(self, text: str, fmt: str) -> dict:
        from pydantic import BaseModel, Field

        class _Item(BaseModel):
            item: str
            quantity: int = 0
            unit_price: Optional[float] = None
            line_total: Optional[float] = None
            note: Optional[str] = None

        class _Extraction(BaseModel):
            invoice_number: Optional[str] = Field(None)
            vendor: Optional[str] = None
            amount: Optional[float] = Field(None, description="stated grand total")
            currency: str = "USD"
            due_date: Optional[str] = Field(None, description="ISO YYYY-MM-DD or null if unparseable")
            raw_due_date_text: Optional[str] = None
            subtotal: Optional[float] = None
            tax_amount: Optional[float] = None
            other_charges: Optional[float] = Field(None, description="shipping/handling/fees")
            items: list[_Item] = Field(default_factory=list)

        prompt = (
            "You are an invoice data-extraction engine. Extract fields EXACTLY as a "
            "human would read them, fixing only obvious corruption:\n"
            "- OCR errors: letter O/o -> digit 0 inside numbers ('2O26'->'2026', '$3,500.O0'->'3500.00').\n"
            "- Canonicalize item names by removing internal spaces in Widget/Gadget SKUs "
            "('Widget A'->'WidgetA', 'Gadget X'->'GadgetX'); keep other names verbatim "
            "(SuperGizmo, WidgetC, MegaSprocket).\n"
            "- Quantities written as 'x12' or 'qty: 10' are integers.\n"
            "- If the document is an email, extract the invoice inside the body.\n"
            "- Convert dates to ISO; if a date is relative/unparseable (e.g. 'yesterday'), "
            "set due_date=null and put the original in raw_due_date_text.\n"
            "- Capture shipping/handling as other_charges separately from tax.\n"
            "- NEVER invent missing values; use null. Do not 'fix' negative quantities.\n\n"
            f"FORMAT: {fmt}\nDOCUMENT:\n{text}"
        )
        structured = self.llm.with_structured_output(_Extraction, method="function_calling")
        last_err = None
        for attempt in range(2):
            try:
                p = prompt if attempt == 0 else (
                    prompt + f"\n\nYour previous attempt was rejected ({last_err}). "
                    "The document DOES contain line items - re-extract every item row carefully.")
                res: _Extraction = structured.invoke(p)
                d = res.model_dump()
                for k in ("amount", "subtotal", "tax_amount", "other_charges"):
                    d[k] = parse_money(d[k])
                for it in d["items"]:
                    it["unit_price"] = parse_money(it["unit_price"])
                    it["line_total"] = parse_money(it["line_total"])
                if d["items"] or not text.strip():
                    d["extraction_method"] = f"llm:{self.name}" + (f" (retry {attempt})" if attempt else "")
                    d["extraction_warnings"] = []
                    return d
                last_err = "no line items extracted"
            except Exception as e:
                last_err = e
        d = self._mock.extract(text, fmt)
        d.setdefault("extraction_warnings", []).append(
            f"LLM extraction fell back to heuristic ({last_err})")
        return d

    def assess_fraud(self, facts: dict, *, inv=None, validation=None, db_path=None, **_) -> dict:
        from pydantic import BaseModel, Field
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        from . import db as _db

        tool_log: list[str] = []

        @tool
        def check_inventory(item: str) -> str:
            r = _db.query_inventory(item, db_path or _db.DEFAULT_DB)
            out = f"{item}: stock={r['stock']}, in_catalog={r['found']}"
            tool_log.append(f"check_inventory({item!r}) -> {out}")
            return out

        @tool
        def recompute_total() -> str:
            out = (f"recomputed={getattr(validation, 'recomputed_total', None)}, "
                   f"stated={getattr(validation, 'stated_total', None)}, "
                   f"delta={getattr(validation, 'total_delta', None)}")
            tool_log.append(f"recompute_total() -> {out}")
            return out

        fns = {"check_inventory": check_inventory, "recompute_total": recompute_total}

        class _Fraud(BaseModel):
            extra_signals: list[str] = Field(default_factory=list)
            extra_risk: int = Field(0, description="0-40 additional risk points")

        try:
            bound = self.llm.bind_tools(list(fns.values()))
            msgs = [
                SystemMessage("You are an AP fraud/risk analyst. Use the tools to VERIFY the "
                              "claimed stock for each line item and to recompute the total "
                              "before you judge. Call tools as needed, then stop."),
                HumanMessage(f"Review this invoice and gather evidence with the tools:\n{facts}"),
            ]
            for _i in range(4):
                ai = bound.invoke(msgs)
                msgs.append(ai)
                calls = getattr(ai, "tool_calls", None) or []
                if not calls:
                    break
                for tc in calls:
                    fn = fns.get(tc["name"])
                    result = fn.invoke(tc.get("args", {})) if fn else "unknown tool"
                    msgs.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            findings = "\n".join(tool_log) or "no tool findings"
            verdict: _Fraud = self.llm.with_structured_output(_Fraud, method="function_calling").invoke(
                "You are an AP fraud/risk analyst. Using the verified tool findings below, list "
                "any ADDITIONAL fraud/risk signals a rules engine might miss and assign 0-40 "
                "extra risk points (be conservative).\n\n"
                f"INVOICE FACTS: {facts}\nVERIFIED FINDINGS:\n{findings}")
            return {"extra_signals": list(verdict.extra_signals),
                    "extra_risk": max(0, min(40, verdict.extra_risk)), "tool_log": tool_log}
        except Exception:
            return {"extra_signals": [], "extra_risk": 0, "tool_log": tool_log}

    def write_vp_memo(self, facts: dict, decision: str) -> str:
        prompt = (
            f"You are a VP approving/rejecting a vendor invoice. The decision is {decision}. "
            "Write a concise 2-3 sentence rationale a CFO would accept, grounded ONLY in "
            f"these facts (do not change the decision):\n{facts}"
        )
        try:
            return self.llm.invoke(prompt).content.strip()
        except Exception:
            return self._mock.write_vp_memo(facts, decision)

    def write_reflection(self, facts: dict, decision: str) -> str:
        prompt = (
            f"Critically reflect on the proposed decision ({decision}) for this invoice. "
            "Is it consistent with the evidence? Note any overlooked risk in 1-2 sentences. "
            f"Do not restate the decision.\nFACTS: {facts}"
        )
        try:
            return self.llm.invoke(prompt).content.strip()
        except Exception:
            return self._mock.write_reflection(facts, decision)


def get_reasoner(provider: Optional[str] = None, *, verbose: bool = False) -> Reasoner:
    prov = (provider or os.environ.get("LLM_PROVIDER", "mock")).strip().lower()
    if prov in ("", "mock", "none"):
        return MockReasoner()
    if prov not in PROVIDERS:
        if verbose:
            print(f"[llm] unknown provider {prov!r}; using mock")
        return MockReasoner()
    cfg = PROVIDERS[prov]
    if cfg["key"] and not os.environ.get(cfg["key"]):
        if verbose:
            print(f"[llm] {cfg['key']} not set for provider {prov!r}; falling back to mock")
        return MockReasoner()
    try:
        return LLMReasoner(prov)
    except Exception as e:
        if verbose:
            print(f"[llm] failed to init {prov!r} ({e}); using mock")
        return MockReasoner()
