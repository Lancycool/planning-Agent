import copy
from pathlib import Path
from uuid import uuid4

import pytest

from content_agent.engine import Agent
from content_agent.models import MockModel
from content_agent.schemas import Request, Scenario
from content_agent.storage import Store
from content_agent.tools import load_catalog

ROOT = Path(__file__).resolve().parents[1]
BASE = {"request_id": "test-001", "theme": "字幕产品活动", "budget": 20,
        "deadline": "2026-10-29T18:00:00+08:00"}
CLOCK = "2026-10-29T17:00:00+08:00"


@pytest.fixture
def tmp_path():
    # Windows managed sandboxes may reject pytest's mode=0o700 directories.
    # Keep isolated test artifacts inside the ignored workspace runtime folder.
    path = ROOT / ".runtime" / "test-work" / uuid4().hex
    path.mkdir(parents=True)
    return path


@pytest.fixture
def run_agent(tmp_path):
    store = Store(tmp_path / "tasks.sqlite3")
    catalog = load_catalog(ROOT / "data/catalog.json")

    def run(updates=None, config=None, model=None):
        agent = Agent(store, model or MockModel(), copy.deepcopy(catalog))
        result = agent.run(Request.model_validate({**BASE, **(updates or {})}),
                           Scenario.model_validate({"start_at": CLOCK, **(config or {})}))
        return result, store, agent

    yield run
    store.close()
