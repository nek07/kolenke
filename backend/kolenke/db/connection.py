"""SQLite access. One short connection per call behind a process-wide lock: the API, the job runner and the
scheduler run in different threads, and SQLite allows a single writer."""
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime

from kolenke.config import get_config

_lock = threading.RLock()

Row = dict
Args = Sequence | dict


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_config().db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Several statements that must succeed or fail together."""
    with _lock:
        conn = _connect()
        try:
            with conn:  # commits, or rolls back on error
                yield conn
        finally:
            conn.close()


def query(sql: str, args: Args = ()) -> list[Row]:
    with transaction() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql: str, args: Args = ()) -> Row | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def scalar(sql: str, args: Args = ()):
    with transaction() as c:
        row = c.execute(sql, args).fetchone()
        return row[0] if row else None


def execute(sql: str, args: Args = ()) -> int:
    """Returns the number of changed rows."""
    with transaction() as c:
        return c.execute(sql, args).rowcount


def insert(sql: str, args: Args = ()) -> int | None:
    """Returns the new row id, or None when INSERT OR IGNORE skipped a duplicate."""
    with transaction() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid if cur.rowcount else None


def placeholders(items: Sequence) -> str:
    return ",".join("?" * len(items))


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
