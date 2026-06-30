from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from invoice_ai import db
from invoice_ai.config import Settings
from invoice_ai.llm import PROVIDERS, get_reasoner
from invoice_ai.models import Decision
from invoice_ai.pipeline import (list_invoice_files, run_batch, run_one, run_one_obj,
                                 summarize)
from invoice_ai.ingestion import ingest
from invoice_ai.validation import validate
from invoice_ai.approval import baseline
from invoice_ai.payment import settle
import os

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(ROOT / "inventory.db")
FOLDERS = {"sample": str(ROOT / "data" / "invoices"),
           "custom": str(ROOT / "data" / "custom_invoices")}

app = FastAPI(title="Galatiq Invoice AP Automation", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _settings() -> Settings:
    s = Settings(db_path=DB_PATH, runs_dir=str(ROOT / "runs"))
    if not Path(DB_PATH).exists():
        from setup_db import seed_inventory
        seed_inventory(DB_PATH)
    return s


def _jsonable(res) -> dict:
    return res.model_dump(mode="json")


class ProcessReq(BaseModel):
    path: str
    provider: Optional[str] = None


class BatchReq(BaseModel):
    folder: str = "sample"
    provider: Optional[str] = None


class OverrideReq(BaseModel):
    path: str
    decision: str
    note: Optional[str] = None
    provider: Optional[str] = None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/providers")
def providers():
    out = [{"id": "mock", "label": "Mock (offline, no key)", "ready": True}]
    for pid, cfg in PROVIDERS.items():
        ready = (cfg["key"] is None) or bool(os.environ.get(cfg["key"]))
        out.append({"id": pid, "label": pid, "ready": ready,
                    "needs_key": cfg["key"]})
    return out


@app.get("/api/inventory")
def inventory():
    _settings()
    return db.all_inventory(DB_PATH)


@app.get("/api/invoices")
def invoices():
    out = []
    for group, folder in FOLDERS.items():
        if Path(folder).exists():
            for p in list_invoice_files(folder):
                out.append({"group": group, "path": p, "name": Path(p).name,
                            "format": Path(p).suffix.lstrip(".")})
    return out


@app.post("/api/process")
def process(req: ProcessReq):
    res = run_one(req.path, get_reasoner(req.provider), _settings())
    return _jsonable(res)


@app.post("/api/batch")
def batch(req: BatchReq):
    folder = FOLDERS.get(req.folder, FOLDERS["sample"])
    paths = list_invoice_files(folder)
    results = run_batch(paths, get_reasoner(req.provider), _settings())
    return {"results": [_jsonable(r) for r in results],
            "summary": {k: str(v) for k, v in summarize(results).items()}}


@app.post("/api/override")
def override(req: OverrideReq):
    settings = _settings()
    reasoner = get_reasoner(req.provider)
    inv = ingest(req.path, reasoner)
    rep = validate(inv, settings.db_path)
    appr = baseline(inv, rep, reasoner, settings)
    appr.decision = Decision.APPROVE if req.decision.upper() == "APPROVE" else Decision.REJECT
    appr.revised = True
    appr.rationale = f"Human override: {req.note or req.decision}. " + appr.rationale
    res = settle(inv, rep, appr, settings)
    return _jsonable(res)


@app.post("/api/reset")
def reset():
    from setup_db import seed_inventory
    seed_inventory(DB_PATH)
    db.ensure_ledger(DB_PATH)
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("DELETE FROM processing_log")
    conn.execute("DELETE FROM invoice_ledger")
    conn.commit(); conn.close()
    return {"status": "reset"}
