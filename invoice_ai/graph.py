from __future__ import annotations

from typing import Optional

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from . import approval as approval_mod
from . import ingestion, payment, validation
from .config import Settings
from .llm import Reasoner
from .models import ApprovalDecision, Decision, Invoice, ProcessingResult, ValidationReport


class GraphState(TypedDict, total=False):
    invoice_path: str
    invoice: Invoice
    validation: ValidationReport
    approval: ApprovalDecision
    result: ProcessingResult
    reflection_count: int
    reflect_changed: bool
    logs: list[dict]


def build_graph(reasoner: Reasoner, settings: Settings):

    def _log(state: GraphState, node: str, msg: str) -> list[dict]:
        logs = list(state.get("logs", []))
        logs.append({"node": node, "msg": msg})
        return logs

    def ingest_node(state: GraphState) -> GraphState:
        inv = state.get("invoice") or ingestion.ingest(state["invoice_path"], reasoner)
        return {"invoice": inv,
                "logs": _log(state, "ingest",
                             f"{inv.source_format} -> {inv.invoice_number} "
                             f"({len(inv.items)} items, via {inv.extraction_method})")}

    def validate_node(state: GraphState) -> GraphState:
        rep = validation.validate(state["invoice"], settings.db_path)
        return {"validation": rep,
                "logs": _log(state, "validate",
                             f"{rep.status}: {len(rep.issues)} issue(s)")}

    def approve_node(state: GraphState) -> GraphState:
        appr = approval_mod.baseline(state["invoice"], state["validation"], reasoner, settings)
        return {"approval": appr, "reflection_count": 0,
                "logs": _log(state, "approve",
                             f"baseline={appr.decision.value} risk={appr.risk_score}")}

    def reflect_node(state: GraphState) -> GraphState:
        prev = state["approval"]
        appr = approval_mod.reflect_step(
            state["invoice"], state["validation"], prev, reasoner, settings)
        changed = appr.decision != prev.decision
        return {"approval": appr,
                "reflection_count": state.get("reflection_count", 0) + 1,
                "reflect_changed": changed,
                "logs": _log(state, "reflect",
                             f"final={appr.decision.value}"
                             + (" (revised)" if changed else ""))}

    def after_reflect(state: GraphState) -> str:
        if state.get("reflect_changed") and state.get("reflection_count", 0) < settings.max_reflections:
            return "reflect"
        return "pay" if state["approval"].decision == Decision.APPROVE else "reject"

    def pay_node(state: GraphState) -> GraphState:
        res = payment.settle(state["invoice"], state["validation"], state["approval"], settings)
        msg = f"PAID {res.payment['payment_id']}" if res.payment else f"not paid ({res.status})"
        return {"result": res, "logs": _log(state, "pay", msg)}

    def reject_node(state: GraphState) -> GraphState:
        res = payment.settle(state["invoice"], state["validation"], state["approval"], settings)
        return {"result": res, "logs": _log(state, "reject", f"{res.status}")}

    g = StateGraph(GraphState)
    g.add_node("ingest", ingest_node)
    g.add_node("validate", validate_node)
    g.add_node("approve", approve_node)
    g.add_node("reflect", reflect_node)
    g.add_node("pay", pay_node)
    g.add_node("reject", reject_node)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "validate")
    g.add_edge("validate", "approve")
    g.add_edge("approve", "reflect")
    g.add_conditional_edges("reflect", after_reflect,
                            {"reflect": "reflect", "pay": "pay", "reject": "reject"})
    g.add_edge("pay", END)
    g.add_edge("reject", END)
    return g.compile()


def process_invoice(path: str, reasoner: Reasoner, settings: Settings,
                    invoice: Optional[Invoice] = None) -> ProcessingResult:
    graph = build_graph(reasoner, settings)
    init: GraphState = {"invoice_path": path, "logs": []}
    if invoice is not None:
        init["invoice"] = invoice
    final = graph.invoke(init)
    result: ProcessingResult = final["result"]
    result.logs = final.get("logs", [])
    return result
