"""History of one vacancy (side panel) and the global activity log."""
from kolenke.db.connection import execute, now, query


def add(vacancy_id: int, kind: str, text: str) -> None:
    execute("INSERT INTO events(vacancy_id, ts, kind, text) VALUES (?, ?, ?, ?)", (vacancy_id, now(), kind, text))


def for_vacancy(vacancy_id: int) -> list[dict]:
    return query("SELECT ts, kind, text FROM events WHERE vacancy_id=? ORDER BY id", (vacancy_id,))


AUTOPILOT_QUEUED = "Автопилот поставил в очередь"


def queued_by_autopilot(vacancy_id: int) -> bool:
    """True when the last time the vacancy went into the queue, the autopilot put it there (not you)."""
    rows = query("SELECT text FROM events WHERE vacancy_id=? AND kind='queued' ORDER BY id DESC LIMIT 1", (vacancy_id,))
    return bool(rows) and rows[0]["text"] == AUTOPILOT_QUEUED


def log(msg: str) -> None:
    print(msg, flush=True)
    execute("INSERT INTO log(ts, msg) VALUES (?, ?)", (now(), msg))


def recent_log(limit: int = 80) -> list[dict]:
    return query("SELECT ts, msg FROM log ORDER BY id DESC LIMIT ?", (limit,))
