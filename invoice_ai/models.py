from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item: str
    quantity: int = 0
    unit_price: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    note: Optional[str] = None


class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    invoice_number: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[Decimal] = Field(default=None, description="Stated grand total")
    currency: str = "USD"
    date: Optional[str] = None
    due_date: Optional[str] = None
    raw_due_date_text: Optional[str] = None
    items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    other_charges: Optional[Decimal] = None
    revision: Optional[str] = None
    notes: Optional[str] = None
    source_format: Optional[str] = None
    source_path: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_warnings: list[str] = Field(default_factory=list)


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    FAIL = "FAIL"


class Issue(BaseModel):
    code: str
    detail: str
    severity: Severity
    item: Optional[str] = None


class ValidationReport(BaseModel):
    status: str = "PASS"
    issues: list[Issue] = Field(default_factory=list)
    aggregated_items: dict[str, int] = Field(default_factory=dict)
    recomputed_total: Optional[Decimal] = None
    stated_total: Optional[Decimal] = None
    total_delta: Optional[Decimal] = None
    superseded: bool = False
    superseded_by: Optional[str] = None

    @property
    def has_fail(self) -> bool:
        return any(i.severity == Severity.FAIL for i in self.issues)

    def add(self, code: str, detail: str, severity: Severity, item: Optional[str] = None) -> None:
        self.issues.append(Issue(code=code, detail=detail, severity=severity, item=item))


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class ApprovalDecision(BaseModel):
    decision: Decision
    rationale: str = ""
    risk_score: int = 0
    fraud_signals: list[str] = Field(default_factory=list)
    high_scrutiny: bool = False
    reflection: Optional[str] = None
    revised: bool = False
    tool_calls: list[str] = Field(default_factory=list)


class ProcessingResult(BaseModel):
    invoice: Invoice
    validation: Optional[ValidationReport] = None
    approval: Optional[ApprovalDecision] = None
    payment: Optional[dict[str, Any]] = None
    status: str = "OK"
    amount_at_risk: Optional[Decimal] = None
    dedup_reason: Optional[str] = None
    logs: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
