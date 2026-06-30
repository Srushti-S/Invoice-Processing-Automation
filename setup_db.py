from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

SEED = [
    ("WidgetA", 15),
    ("WidgetB", 10),
    ("GadgetX", 5),
    ("FakeItem", 0),
]


def seed_inventory(db_path: str = "inventory.db") -> list[tuple[str, int]]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS inventory (item TEXT PRIMARY KEY, stock INTEGER)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS processing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT,
                vendor TEXT,
                amount REAL,
                currency TEXT,
                decision TEXT,
                reason TEXT,
                payment_id TEXT,
                created_at TEXT
            )
            """
        )
        cur.executemany("INSERT OR REPLACE INTO inventory VALUES (?, ?)", SEED)
        conn.commit()
        rows = cur.execute("SELECT item, stock FROM inventory ORDER BY item").fetchall()
        return rows
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Seed the mock inventory DB.")
    ap.add_argument("--db", default="inventory.db", help="SQLite file path")
    args = ap.parse_args()
    rows = seed_inventory(args.db)
    print(f"Seeded {Path(args.db).resolve()}")
    for item, stock in rows:
        print(f"  {item:<10} stock={stock}")
