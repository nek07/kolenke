"""Tests run on a throwaway data folder: no hh, no Gmail, no Mac notifications, your real database is untouched."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["JOBBOT_DATA"] = tempfile.mkdtemp(prefix="jobbot-test-")
os.environ["JOBBOT_NO_BACKGROUND"] = "1"
os.environ["RELAY_DATA"] = tempfile.mkdtemp(prefix="relay-test-")

import db  # noqa: E402  (must come after the env vars)

TABLES = ["vacancies", "companies", "answers", "questions", "chat_items", "events", "log", "settings"]


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    """Every test starts from an empty database with default settings and answer topics."""
    for t in TABLES:
        db.x(f"DELETE FROM {t}") if db.q("SELECT name FROM sqlite_master WHERE name=?", (t,)) else None
    db.init()
    import chat_bot
    notes = []
    monkeypatch.setattr(chat_bot, "notify", notes.append)  # never pop up real notifications
    yield notes


def add_vacancy(**kw):
    """Insert a vacancy row and return its id."""
    row = {"source": "hh", "ext_id": "1", "url": f"https://hh.kz/vacancy/{kw.get('ext_id', '1')}", "title": "Backend",
           "company": "ТОО Тест", "status": "new", "created_at": db.now()}
    row.update(kw)
    cols = ", ".join(row)
    db.x(f"INSERT INTO vacancies({cols}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
    return db.q("SELECT id FROM vacancies WHERE url=?", (row["url"],))[0]["id"]


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import app as app_module
    c = TestClient(app_module.app, base_url="http://127.0.0.1:8765")
    c.headers.update({"X-JobBot": "1"})
    return c
