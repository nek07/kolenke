"""Companies to send the resume to by e-mail."""
from datetime import date

from kolenke.db.connection import execute, insert, now, one, placeholders, query, scalar


def find(status: str | None = None) -> list[dict]:
    if status:
        return query("SELECT * FROM companies WHERE status=? ORDER BY id DESC", (status,))
    return query("SELECT * FROM companies ORDER BY id DESC")


def get(cid: int) -> dict | None:
    return one("SELECT * FROM companies WHERE id=?", (cid,))


def add(name: str, email: str, position: str) -> int | None:
    """None when the e-mail is already in the list."""
    return insert("INSERT OR IGNORE INTO companies(name, email, position, created_at) VALUES (?, ?, ?, ?)",
                  (name, email, position, now()))


def update(cid: int, name: str, position: str) -> int:
    return execute("UPDATE companies SET name=?, position=? WHERE id=?", (name, position, cid))


def set_status(ids: list[int], status: str) -> None:
    execute(f"UPDATE companies SET status=? WHERE id IN ({placeholders(ids)})", [status, *ids])


def delete(ids: list[int]) -> None:
    execute(f"DELETE FROM companies WHERE id IN ({placeholders(ids)})", ids)


def queued() -> list[dict]:
    return query("SELECT * FROM companies WHERE status='queued' ORDER BY id")


def mark_sent(cid: int) -> None:
    execute("UPDATE companies SET status='sent', note=NULL, sent_at=? WHERE id=?", (now(), cid))


def mark_error(cid: int, note: str) -> None:
    execute("UPDATE companies SET status='error', note=? WHERE id=?", (note[:300], cid))


def sent_today() -> int:
    return scalar("SELECT COUNT(*) FROM companies WHERE status='sent' AND sent_at LIKE ?", (date.today().isoformat() + "%",))


def count_by_status() -> dict[str, int]:
    return {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM companies GROUP BY status")}


def all_for_search() -> list[dict]:
    return query("SELECT id, name, email, position, status FROM companies ORDER BY id DESC")
