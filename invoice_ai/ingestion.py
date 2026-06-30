from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .llm import Reasoner
from .models import Invoice, LineItem
from .normalize import canon_item, item_note, parse_date, parse_int, parse_money

STRUCTURED = {".json", ".xml", ".csv"}
TEXTUAL = {".txt", ".pdf"}


def detect_format(path: str) -> str:
    return Path(path).suffix.lower().lstrip(".")


def _to_line_items(raw_items: list[dict]) -> list[LineItem]:
    out: list[LineItem] = []
    for it in raw_items or []:
        name = str(it.get("item") or it.get("name") or "").strip()
        if not name:
            continue
        note = it.get("note") or item_note(name)
        out.append(LineItem(
            item=canon_item(name),
            quantity=parse_int(it.get("quantity", it.get("qty", 0))) or 0,
            unit_price=parse_money(it.get("unit_price")),
            line_total=parse_money(it.get("line_total", it.get("amount"))),
            note=note,
        ))
    return out


def build_invoice(data: dict, *, fmt: str, path: str, method: str) -> Invoice:
    due_iso, due_raw = (data.get("due_date"), data.get("raw_due_date_text"))
    if due_iso and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(due_iso)):
        due_iso, due_raw = parse_date(str(due_iso))
    return Invoice(
        invoice_number=data.get("invoice_number"),
        vendor=(data.get("vendor") or None),
        amount=parse_money(data.get("amount")),
        currency=(data.get("currency") or "USD"),
        date=data.get("date"),
        due_date=due_iso,
        raw_due_date_text=due_raw or data.get("raw_due_date_text"),
        items=_to_line_items(data.get("items", [])),
        subtotal=parse_money(data.get("subtotal")),
        tax_rate=parse_money(data.get("tax_rate")),
        tax_amount=parse_money(data.get("tax_amount")),
        other_charges=parse_money(data.get("other_charges")),
        revision=data.get("revision"),
        notes=data.get("notes"),
        source_format=fmt,
        source_path=path,
        extraction_method=method,
        extraction_warnings=list(data.get("extraction_warnings", [])),
    )


def _parse_json(text: str) -> dict:
    obj = json.loads(text)
    vendor = obj.get("vendor")
    if isinstance(vendor, dict):
        vendor = vendor.get("name")
    items = obj.get("line_items") or obj.get("items") or []
    return {
        "invoice_number": obj.get("invoice_number"),
        "vendor": vendor,
        "amount": obj.get("total", obj.get("amount")),
        "currency": obj.get("currency", "USD"),
        "date": obj.get("date"),
        "due_date": obj.get("due_date"),
        "subtotal": obj.get("subtotal"),
        "tax_rate": obj.get("tax_rate"),
        "tax_amount": obj.get("tax_amount"),
        "other_charges": obj.get("shipping", obj.get("other_charges")),
        "revision": obj.get("revision"),
        "notes": obj.get("notes"),
        "items": items,
    }


def _parse_xml(text: str) -> dict:
    root = ET.fromstring(text)

    def find(tag):
        el = root.find(f".//{tag}")
        return el.text.strip() if el is not None and el.text else None

    items = []
    for it in root.findall(".//line_items/item"):
        items.append({
            "item": (it.findtext("name") or "").strip(),
            "quantity": it.findtext("quantity"),
            "unit_price": it.findtext("unit_price"),
        })
    return {
        "invoice_number": find("invoice_number"),
        "vendor": find("vendor"),
        "amount": find("total"),
        "currency": find("currency") or "USD",
        "date": find("date"),
        "due_date": find("due_date"),
        "subtotal": find("subtotal"),
        "tax_rate": find("tax_rate"),
        "tax_amount": find("tax_amount"),
        "items": items,
    }


def _parse_csv(text: str) -> dict:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {"items": []}
    header = [c.strip().lower() for c in rows[0]]

    if header[:2] == ["field", "value"]:
        data: dict = {"items": []}
        cur: dict = {}
        for row in rows[1:]:
            if len(row) < 2:
                continue
            f, v = row[0].strip().lower(), row[1].strip()
            if f == "item":
                if cur:
                    data["items"].append(cur)
                cur = {"item": v}
            elif f in ("quantity", "qty"):
                cur["quantity"] = v
            elif f in ("unit_price", "unit price", "price"):
                cur["unit_price"] = v
            elif f in ("invoice_number", "invoice number"):
                data["invoice_number"] = v
            elif f == "vendor":
                data["vendor"] = v
            elif f == "date":
                data["date"] = v
            elif f in ("due_date", "due date"):
                data["due_date"] = v
            elif f == "subtotal":
                data["subtotal"] = v
            elif f == "tax":
                data["tax_amount"] = v
            elif f == "total":
                data["amount"] = v
        if cur:
            data["items"].append(cur)
        return data

    reader = csv.DictReader(io.StringIO(text))
    data = {"items": []}
    for row in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        item = norm.get("item", "")
        qty = norm.get("qty", norm.get("quantity", ""))
        if item and qty:
            data["items"].append({
                "item": item, "quantity": qty,
                "unit_price": norm.get("unit price", norm.get("unit_price")),
                "line_total": norm.get("line total", norm.get("line_total")),
            })
            data.setdefault("invoice_number", norm.get("invoice number"))
            data.setdefault("vendor", norm.get("vendor"))
            data.setdefault("date", norm.get("date"))
            data.setdefault("due_date", norm.get("due date"))
        else:
            label = norm.get("unit price", "").lower()
            val = norm.get("line total", "")
            if "subtotal" in label:
                data["subtotal"] = val
            elif "tax" in label:
                data["tax_amount"] = val
                m = re.search(r"(\d+(?:\.\d+)?)\s*%", label)
                if m:
                    data["tax_rate"] = str(Decimal(m.group(1)) / 100)
            elif "total" in label:
                data["amount"] = val
    return data


def _read_pdf_text(path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        try:
            import fitz
            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        except Exception:
            return ""


def ingest(path: str, reasoner: Reasoner) -> Invoice:
    fmt = detect_format(path)
    p = Path(path)
    if fmt == "json":
        return build_invoice(_parse_json(p.read_text(encoding="utf-8-sig")), fmt=fmt, path=path, method="structured")
    if fmt == "xml":
        return build_invoice(_parse_xml(p.read_text(encoding="utf-8-sig")), fmt=fmt, path=path, method="structured")
    if fmt == "csv":
        return build_invoice(_parse_csv(p.read_text(encoding="utf-8-sig")), fmt=fmt, path=path, method="structured")
    text = _read_pdf_text(path) if fmt == "pdf" else p.read_text(encoding="utf-8-sig")
    data = reasoner.extract(text, fmt)
    inv = build_invoice(data, fmt=fmt, path=path, method=data.get("extraction_method", "llm"))
    if not text.strip():
        inv.extraction_warnings.append("empty document text")
    return inv
