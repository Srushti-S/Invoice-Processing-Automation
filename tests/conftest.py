import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from setup_db import seed_inventory
from invoice_ai.config import Settings
from invoice_ai.llm import MockReasoner


@pytest.fixture
def settings(tmp_path):
    db = str(tmp_path / "inventory.db")
    seed_inventory(db)
    return Settings(db_path=db, runs_dir=str(tmp_path / "runs"))


@pytest.fixture
def reasoner():
    return MockReasoner()
