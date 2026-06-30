from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

_KNOWN_PREFIXES = ("Widget", "Gadget")

_SKIP_LINE = re.compile(
    r"(?i)\b(subtotal|sub total|tax|total|amount due|grand total|balance|"
    r"description|qty\b.*\b(rate|price|amount)|item\b.*\b(qty|price)|"
    r"payment terms|terms:|thank you|notes?:|deliver|contact|attn|"
    r"bill to|ship to|^to:|^from:|invoice|date|due)\b"
)
_DIVIDER = re.compile(r"^[\s\-=_*.]+$")


_MONEY_SYM = "$€£¥"
_CURRENCY_SYMBOLS = {"€": "EUR", "£": "GBP", "¥": "JPY", "$": "USD"}


def fix_ocr_digits(s: str) -> str:
    def _fix_token(m: re.Match) -> str:
        tok = m.group(0)
        if not any(c.isdigit() for c in tok):
            return tok
        return tok.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")

    return re.sub(r"[0-9OoIl][0-9OoIl,\.]*[0-9OoIl]", _fix_token, s)


def parse_money(s) -> Optional[Decimal]:
    if s is None:
        return None
    if isinstance(s, (int, float, Decimal)):
        try:
            return Decimal(str(s))
        except InvalidOperation:
            return None
    text = fix_ocr_digits(str(s)).strip()
    negative_paren = bool(re.match(r"^\(.*\d.*\)$", text))
    m = re.search(r"-?[$€£¥]?\s*-?[\d,]+(?:\.\d+)?", text)
    if not m:
        return None
    cleaned = re.sub(r"[,$€£¥\s]", "", m.group(0))
    try:
        val = Decimal(cleaned)
        return -val if (negative_paren and val > 0) else val
    except InvalidOperation:
        return None


def parse_int(s) -> Optional[int]:
    if s is None:
        return None
    if isinstance(s, bool):
        return None
    if isinstance(s, (int,)):
        return s
    m = re.search(r"-?\d+", fix_ocr_digits(str(s)))
    return int(m.group(0)) if m else None


def canon_item(name: str) -> str:
    if not name:
        return ""
    n = re.sub(r"\s*\([^)]*\)\s*", " ", name).strip()
    n = re.sub(r"(?i)\b(widget|gadget)\s+([a-z])\b",
               lambda m: m.group(1).capitalize() + m.group(2).upper(), n)
    return n.strip()


def item_note(name: str) -> Optional[str]:
    m = re.search(r"\(([^)]*)\)", name or "")
    return m.group(1).strip() if m else None


def parse_date(s: Optional[str], *, today: Optional[date] = None) -> tuple[Optional[str], Optional[str]]:
    if s is None:
        return None, None
    raw = str(s).strip()
    if not raw:
        return None, raw
    today = today or date.today()
    low = raw.lower()
    if low in {"yesterday"}:
        return None, raw
    if low in {"today", "now"}:
        return today.isoformat(), raw
    txt = fix_ocr_digits(raw)
    fmts = [
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d %Y",
        "%b %d, %Y", "%d-%b-%Y", "%Y/%m/%d", "%m-%d-%Y", "%B %d %Y",
    ]
    cleaned = txt.replace(".", "").strip()
    for fmt in fmts:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat(), raw
        except ValueError:
            continue
    return None, raw


_VENDOR_LABELS = re.compile(r"(?i)^\s*(vendor|vndr|from|supplier|bill from)\s*[:\-]\s*(.+)$")
_INV_LABELS = re.compile(r"(?i)(invoice\s*(?:number|no|#)?|inv\s*(?:no|#)?)\s*[:\-]?\s*(INV[\s\-]?\d+|\d{3,})")
_DUE_LABELS = re.compile(r"(?i)\b(due\s*date|due\s*dt|due)\s*[:\-]\s*(.+)$")
_DATE_LABELS = re.compile(r"(?i)(?<!due )\bdate\b\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9,\-/ ]*?)(?:\s{2,}|$)")
_TOTAL_LABELS = re.compile(r"(?i)\b(total\s*amount|grand\s*total|total|amt)\s*[:\-]?\s*[$€£¥]?\s*([\d,OolI]+(?:\.\d+)?)")
_SUBTOTAL_LABELS = re.compile(r"(?i)\bsub\s*total\s*[:\-]?\s*[$€£¥]?\s*([\d,OolI]+(?:\.\d+)?)")
_TAX_LABELS = re.compile(r"(?i)\b(?:sales\s*)?tax\b[^$€£¥]*?[$€£¥]\s*([\d,OolI]+(?:\.\d+)?)")
_SHIP_LABELS = re.compile(r"(?i)\b(shipping|handling|freight)\b[^$€£¥\d]*[$€£¥]?\s*([\d,OolI]+(?:\.\d+)?)")
_CURRENCY = re.compile(r"\b(USD|EUR|GBP|JPY|CAD)\b")

_ITEM_PATTERNS = [
    re.compile(r"^\s*[-*]\s*([A-Za-z][\w ]*?)\s+x\s*(\d+)\s+[$€£¥]?([\d,]+(?:\.\d+)?)", re.I),
    re.compile(r"^\s*([A-Za-z][\w ]*?)\s+qty:?\s*(\d+)\s+(?:unit\s*price:?\s*|@\s*)?[$€£¥]?([\d,]+(?:\.\d+)?)", re.I),
    re.compile(r"^\s*([A-Za-z][\w ()]*?)\s{2,}(\d+)\s+[$€£¥]?([\d,OolI]+(?:\.\d+)?)\s+[$€£¥]?([\d,OolI]+(?:\.\d+)?)\s*$", re.I),
    re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s+(\d+)\s+[$€£¥]\s*([\d,OolI.]+)\s+[$€£¥]\s*([\d,OolI.]+)(?:\s+(.+))?\s*$", re.I),
]

_HEADER_WORDS = re.compile(
    r"(?i)\b(subtotal|total|tax|qty|quantity|unit\s*price|price|description|"
    r"terms|invoice|vendor|amount|rate|items?)\b")


def _looks_like_item(name: str) -> bool:
    n = name.strip()
    if not n or len(n) > 40:
        return False
    if _HEADER_WORDS.search(n):
        return False
    return bool(re.match(r"^[A-Za-z][\w ()]*$", n))


def extract_from_text(text: str) -> dict:
    warnings: list[str] = []
    lines = text.splitlines()
    vendor = invoice_number = total = subtotal = tax_amount = shipping = None
    due_raw = date_raw = currency = None
    items: list[dict] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line or _DIVIDER.match(line):
            continue

        if vendor is None:
            mv = _VENDOR_LABELS.match(line)
            if mv and "@" not in mv.group(2):
                vraw = re.split(r"\s+(?:Due|Date|Invoice|Terms|Amount|Attn)\s*[:\-]",
                                mv.group(2).strip())[0].strip()
                vendor = vraw or None

        if invoice_number is None:
            mi = _INV_LABELS.search(fix_ocr_digits(line))
            if mi:
                num = re.sub(r"\s+", "-", mi.group(2).strip())
                num = re.sub(r"(?i)^inv-?", "INV-", num)
                if not num.upper().startswith("INV"):
                    num = "INV-" + num
                invoice_number = num.upper().replace("INV--", "INV-")

        if due_raw is None:
            md = _DUE_LABELS.search(line)
            if md:
                due_raw = md.group(2).strip()

        if date_raw is None:
            mdt = _DATE_LABELS.search(line)
            if mdt:
                date_raw = mdt.group(1).strip()

        if currency is None:
            mc = _CURRENCY.search(line)
            if mc:
                currency = mc.group(1)
            else:
                for sym, code in (("€", "EUR"), ("£", "GBP"), ("¥", "JPY")):
                    if sym in line:
                        currency = code
                        break

        ms = _SUBTOTAL_LABELS.search(line)
        if ms:
            subtotal = parse_money(ms.group(1))
        msh = _SHIP_LABELS.search(line)
        if msh:
            shipping = parse_money(msh.group(2))
        mt = _TAX_LABELS.search(line)
        if mt and "rate" not in line.lower():
            val = parse_money(mt.group(1))
            if val is not None and val >= 0:
                tax_amount = val
        mtot = _TOTAL_LABELS.search(line)
        if mtot and not _SUBTOTAL_LABELS.search(line):
            total = parse_money(mtot.group(2)) or total

        iline = fix_ocr_digits(line)
        for pat in _ITEM_PATTERNS:
            m = pat.match(iline)
            if not m:
                continue
            groups = m.groups()
            name = groups[0].strip()
            if not _looks_like_item(name):
                break
            qty = parse_int(groups[1])
            unit = parse_money(groups[2]) if len(groups) >= 3 and groups[2] else None
            line_total = parse_money(groups[3]) if len(groups) >= 4 and groups[3] else None
            note = (groups[4].strip() if len(groups) >= 5 and groups[4] else None) or item_note(name)
            items.append({
                "item": canon_item(name),
                "quantity": qty if qty is not None else 0,
                "unit_price": unit,
                "line_total": line_total,
                "note": note,
            })
            break

    due_iso, due_text = parse_date(due_raw)
    if due_raw and due_iso is None:
        warnings.append(f"unparseable due date: {due_raw!r}")
    date_iso, _ = parse_date(date_raw)
    if not vendor:
        warnings.append("vendor not found in text")
    if not items:
        warnings.append("no line items parsed")

    return {
        "invoice_number": invoice_number,
        "vendor": vendor,
        "amount": total,
        "currency": currency or "USD",
        "date": date_iso or date_raw,
        "due_date": due_iso,
        "raw_due_date_text": due_text,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "other_charges": shipping,
        "items": items,
        "extraction_warnings": warnings,
    }
