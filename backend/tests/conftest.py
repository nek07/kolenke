"""Tests run on a throwaway data folder: no hh, no Gmail, no Mac notifications, your real database is untouched."""
import os
import tempfile
from pathlib import Path

import pytest

os.environ["KOLENKE_DATA_DIR"] = tempfile.mkdtemp(prefix="kolenke-test-")
os.environ["KOLENKE_BACKGROUND"] = "false"

from kolenke import db  # noqa: E402  (must come after the env vars)
from kolenke.config import ensure_dirs, get_config  # noqa: E402
from kolenke.db.connection import execute, insert, now  # noqa: E402
from kolenke.workers.runner import runner  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
FIXTURES = BACKEND / "tests" / "fixtures"
TABLES = ["vacancies", "companies", "answers", "questions", "chat_items", "events", "log", "settings"]

ensure_dirs(get_config())
db.init()


@pytest.fixture(autouse=True)
def notifications(monkeypatch):
    """Every test starts from an empty database with default settings and answer topics.
    Mac notifications are caught instead of shown: the fixture value is the list of their texts."""
    for t in TABLES:
        execute(f"DELETE FROM {t}")
    db.init()
    runner.stop_requested = False  # «Стоп» pressed in one test must not end tasks in the next
    from kolenke.services import notify
    shown = []
    monkeypatch.setattr(notify, "_osascript", lambda args: shown.append(args[-1]))
    yield shown


def add_vacancy(**kw) -> int:
    """Insert a vacancy row and return its id."""
    row = {"source": "hh", "ext_id": "1", "url": f"https://hh.kz/vacancy/{kw.get('ext_id', '1')}", "title": "Backend",
           "company": "ТОО Тест", "status": "new", "created_at": now()}
    row.update(kw)
    return insert(f"INSERT INTO vacancies({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from kolenke.main import app
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        c.headers.update({"X-JobBot": "1"})
        yield c
