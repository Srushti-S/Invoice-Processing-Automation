# Invoice Processing Automation

Automates invoice processing end-to-end: it extracts the data from an invoice,
validates it against an inventory database, decides whether to approve it, and pays
the approved ones. Handles txt, json, csv, xml and pdf, and runs offline by default.

The pipeline runs in four stages (ingestion, validation, approval, payment) built on
LangGraph. The money and stock checks are plain Python, so the decisions are
deterministic and testable; the LLM only does the language work, like reading messy
text and writing the approval note.

## Setup

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

python setup_db.py

`setup_db.py` seeds a local SQLite inventory.

## Running it

One invoice:  `python main.py --invoice_path=data/invoices/invoice_1001.txt`

A whole folder:     `python main.py --batch data/invoices`

The output shows the extracted fields, the validation flags, the approval decision
with its reasoning, and the final payment or rejection. Add `--json` for
machine-readable output.

It uses an offline mock reasoner by default, so no API key is needed. To run it with a
real model, copy `.env.example` to `.env` and set `LLM_PROVIDER` and the matching key.

## Dashboard

`uvicorn api.server:app --port 8000`      # backend

`cd web && npm install && npm run dev`    # frontend

Open `http://localhost:5173`. Each row is an invoice and its decision; click **View** to see the full trace.

## Tests

pytest -q
