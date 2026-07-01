# Invoice Processing Automation

A multi-agent pipeline that reads invoices, checks them against inventory, decides whether
to approve them, and pays the ones that pass. It handles five file formats (txt, json, csv,
xml, pdf), catches the errors and fraud that slip past manual review, and runs offline with
no API key.

Built on LangGraph. The money and stock decisions are plain Python, so they are predictable
and covered by tests; the LLM does the language work, like reading messy text, writing the
approval note, and running a tool-using fraud check.

## Workflow

| Stage | What it does |
|---|---|
| Ingestion | Detects the format and pulls out vendor, amount, line items, and due date. json/xml/csv are parsed directly; text and PDFs go through the LLM, with a regex fallback. Fixes OCR slips like `2O26` and spaced SKUs like `Widget A`. |
| Validation | Totals the quantity per item, then checks each against the SQLite inventory for unknown, out-of-stock, and over-ordered items. It also re-adds the invoice (`subtotal + tax + fees`) to catch totals that do not reconcile. |
| Approval | A rule-based VP decision with a 0 to 100 fraud score. Invoices over $10K get extra scrutiny. A reflection step re-checks the call and can route a borderline approval to a human. |
| Payment | Approved invoices call a mock payment function; rejections are logged with their reasoning. A ledger blocks paying the same invoice twice, even across separate runs. |

The decision to pay or not never depends on the model. Stock, totals, the threshold, and
the final payment gate are all deterministic code, so the outcome is the same with or
without an LLM, and a bad model response cannot release a payment. The model's risk input
is capped and can only add caution.

## Why it matters

Acme loses roughly $2M a year to manual invoice processing, with a 30% error rate and a
five-day cycle. This runs the same invoices in seconds and stops the ones that would cost
money.

Over the 20 sample invoices it pays the 8 legitimate ones ($44,475) and holds back
$196,310.80 that would otherwise have gone out on fraud, duplicates, over-orders, and bad
data. Some of what it catches:

| Invoice | Problem | Result |
|---|---|---|
| INV-1003 | "Fraudster LLC", an out-of-stock item, due "yesterday" | Rejected, risk 100 |
| INV-1013 | One item split across several lines to get past the stock limit; total padded $50 | Rejected |
| INV-1007 | Total quietly $110 short of its own line items | Rejected |
| INV-1004 | The same invoice submitted twice in different formats | Paid once, duplicate blocked |
| INV-1009 | Empty vendor, negative quantity, negative total | Rejected |

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python setup_db.py

python main.py --invoice_path=data/invoices/invoice_1001.txt   # one invoice
python main.py --batch data/invoices                           # all of them
```

Each run prints the extracted fields, the validation flags, the approval decision with its
reasoning, and the payment or rejection. Add `--json` for machine-readable output.

The dashboard shows the same thing in the browser:

```bash
uvicorn api.server:app --port 8000      # backend
cd web && npm install && npm run dev    # frontend at http://localhost:5173
```

Each row is an invoice and its decision; open one for the full trace (extracted fields,
validation flags, the approval reasoning, and the outcome) and a human override.

```bash
pytest -q      # 56 tests, all offline
```

## Using a real model

It runs on an offline mock reasoner by default, so nothing is needed to try it. To use a
real model, copy `.env.example` to `.env` and set `LLM_PROVIDER` and the matching key
(Grok, Groq, Gemini, Ollama, and others). With a real model the fraud check calls two
tools, `check_inventory` and `recompute_total`, to verify stock and the arithmetic before
it scores the invoice, and returns a structured result. `docs/live-tool-call-trace.md` has
a side-by-side of a mock and a live run.

## Scope

The rule I followed: handle every case the sample data actually contains, keep the money
logic deterministic and tested, and leave speculative work out with a note rather than
half-building it. Two things I would add with more time:

- Real currency conversion for the $10K threshold. Non-USD invoices are handled
  conservatively for now (half the threshold, plus a note) instead of guessing a rate.
- OCR for scanned-image PDFs. The sample PDFs are text-based, so it was not needed here.

## Layout

```
invoice_ai/   the pipeline: models, ingestion, validation, approval, payment, graph, llm
main.py       command-line interface
api/          FastAPI backend
web/          React dashboard
tests/        56 offline tests
data/         sample and custom invoices
```
