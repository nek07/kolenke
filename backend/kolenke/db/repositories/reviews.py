"""Resume reviews: the resume text, the status while it runs and the finished report (json)."""
from kolenke.db.connection import execute, insert, now, one, query
from kolenke.services.text import norm

SUMMARY_COLUMNS = ("id, created_at, finished_at, status, progress, role, grade, source_name, use_market, use_ai, score, "
                   "error")


def create(role: str, grade: str, source_name: str, text: str, use_market: bool, use_ai: bool) -> int:
    return insert(
        "INSERT INTO resume_reviews(created_at, status, progress, role, grade, source_name, resume_text, use_market, use_ai) "
        "VALUES (?, 'pending', 'В очереди', ?, ?, ?, ?, ?, ?)",
        (now(), role, grade, source_name, text, int(use_market), int(use_ai)),
    )


def get(rid: int) -> dict | None:
    return one("SELECT * FROM resume_reviews WHERE id=?", (rid,))


def history(limit: int = 50) -> list[dict]:
    return query(f"SELECT {SUMMARY_COLUMNS} FROM resume_reviews ORDER BY id DESC LIMIT ?", (limit,))


def previous_done(rid: int, role_norm: str, grade: str) -> dict | None:
    """The last finished review before this one for the same role and grade: to show what got better."""
    for r in query("SELECT id, role, score, report, resume_text FROM resume_reviews WHERE id < ? AND grade=? AND status='done' "
                   "ORDER BY id DESC LIMIT 20", (rid, grade)):
        if norm(r["role"]) == role_norm:
            return r
    return None


def set_progress(rid: int, text: str) -> None:
    execute("UPDATE resume_reviews SET status='running', progress=? WHERE id=?", (text, rid))


def finish(rid: int, score: int, report_json: str) -> None:
    execute("UPDATE resume_reviews SET status='done', progress=NULL, score=?, report=?, finished_at=? WHERE id=?",
            (score, report_json, now(), rid))


def fail(rid: int, error: str) -> None:
    execute("UPDATE resume_reviews SET status='error', progress=NULL, error=?, finished_at=? WHERE id=?", (error, now(), rid))


def fail_unfinished(reason: str) -> int:
    """After a restart nothing is running any more."""
    return execute("UPDATE resume_reviews SET status='error', progress=NULL, error=? WHERE status IN ('pending','running')",
                   (reason,))


def delete(rid: int) -> int:
    return execute("DELETE FROM resume_reviews WHERE id=?", (rid,))
