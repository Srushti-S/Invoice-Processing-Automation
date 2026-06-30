from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

DEFAULT_DB = "inventory.db"


@contextmanager
def _conn(db_path: str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def query_inventory(item: str, db_path: str = DEFAULT_DB) -> dict:
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT item, stock FROM inventory WHERE item = ? COLLATE NOCASE", (item,)
        ).fetchone()
    if row is None:
        return {"item": item, "stock": None, "found": False}
    return {"item": row["item"], "stock": int(row["stock"]), "found": True}


def all_inventory(db_path: str = DEFAULT_DB) -> list[dict]:
    with _conn(db_path) as conn:
        rows = conn.execute("SELECT item, stock FROM inventory ORDER BY item").fetchall()
    return [{"item": r["item"], "stock": int(r["stock"])} for r in rows]


def ensure_ledger(db_path: str = DEFAULT_DB) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoice_ledger (
                invoice_number TEXT,
                revision TEXT,
                total TEXT,            -- exact Decimal string, not float
                status TEXT,           -- PAID | REJECTED | NEEDS_HUMAN_REVIEW | ...
                payment_id TEXT,
                superseded INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        try:
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_paid
                   ON invoice_ledger(invoice_number)
                   WHERE status = 'PAID' AND superseded = 0"""
            )
        except sqlite3.Error:
            pass


def record_ledger(
    *, invoice_number, revision, total, status, payment_id, created_at,
    db_path: str = DEFAULT_DB,
) -> None:
    ensure_ledger(db_path)
    with _conn(db_path) as conn:
        conn.execute(
            """INSERT INTO invoice_ledger
               (invoice_number, revision, total, status, payment_id, superseded, created_at)
               VALUES (?,?,?,?,?,0,?)""",
            (invoice_number, revision, str(total) if total is not None else None,
             status, payment_id, created_at),
        )


def claim_payment(
    *, invoice_number, revision, total, payment_id, created_at,
    db_path: str = DEFAULT_DB,
) -> bool:
    ensure_ledger(db_path)
    try:
        with _conn(db_path) as conn:
            conn.execute(
                """INSERT INTO invoice_ledger
                   (invoice_number, revision, total, status, payment_id, superseded, created_at)
                   VALUES (?,?,?,?,?,0,?)""",
                (invoice_number, revision, str(total) if total is not None else None,
                 "PAID", payment_id, created_at),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def find_paid(invoice_number: str, db_path: str = DEFAULT_DB) -> Optional[dict]:
    if not invoice_number:
        return None
    ensure_ledger(db_path)
    with _conn(db_path) as conn:
        row = conn.execute(
            """SELECT invoice_number, revision, total, payment_id, created_at
               FROM invoice_ledger
               WHERE invoice_number = ? AND status = 'PAID' AND superseded = 0
               ORDER BY created_at DESC LIMIT 1""",
            (invoice_number,),
        ).fetchone()
    return dict(row) if row else None


def record_processing(
    *, invoice_number, vendor, amount, currency, decision, reason,
    payment_id, created_at, db_path: str = DEFAULT_DB,
) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            """INSERT INTO processing_log
               (invoice_number, vendor, amount, currency, decision, reason, payment_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (invoice_number, vendor, float(amount) if amount is not None else None,
             currency, decision, reason, payment_id, created_at),
        )


