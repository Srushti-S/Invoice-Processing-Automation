from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Settings:
    scrutiny_threshold: Decimal = Decimal(os.environ.get("APPROVAL_SCRUTINY_THRESHOLD", "10000"))
    fraud_reject: int = 60
    fraud_review: int = 30
    max_reflections: int = 1
    db_path: str = "inventory.db"
    runs_dir: str = "runs"
    reflection: bool = True
