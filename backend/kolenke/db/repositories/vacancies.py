"""All SQL about vacancies: search results, the apply queue, responses and the pipeline after them."""
import json
from datetime import date

from kolenke.db.connection import execute, insert, now, one, placeholders, query, scalar, transaction
from kolenke.db.migrations import INVITE_STATES
from kolenke.schemas.enums import Stage, VacancyStatus

HH_TO_STAGE = {
    "не просмотрен": Stage.applied, "просмотрен": Stage.viewed, "приглашение": Stage.invited,
    "собеседование": Stage.interview, "выход на работу": Stage.offer, "отказ": Stage.declined,
}
_SQL_STAGE_FROM_HH = "CASE hh_state " + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in HH_TO_STAGE.items()) + " ELSE 'applied' END"


def _json(value) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


# ---------- reading ----------
def get(vid: int) -> dict | None:
    return one("SELECT * FROM vacancies WHERE id=?", (vid,))


def get_by_url(url: str) -> dict | None:
    return one("SELECT * FROM vacancies WHERE url=?", (url,))


def get_by_ext_id(source: str, ext_id: str) -> dict | None:
    return one("SELECT * FROM vacancies WHERE source=? AND ext_id=?", (source, ext_id))


def find(source: str | None = None, status: str | None = None, limit: int = 2000) -> list[dict]:
    sql, args = "SELECT * FROM vacancies WHERE 1=1", []
    if source:
        sql += " AND source=?"
        args.append(source)
    if status:
        sql += " AND status=?"
        args.append(status)
    return query(sql + " ORDER BY id DESC LIMIT ?", [*args, limit])


def review_queue(best_match_first: bool, limit: int = 300) -> list[dict]:
    order = "skill_match IS NULL, skill_match DESC, id DESC" if best_match_first else "id DESC"
    return query(f"SELECT * FROM vacancies WHERE source='hh' AND status='new' ORDER BY {order} LIMIT ?", (limit,))


def apply_queue(best_match_first: bool) -> list[dict]:
    order = "skill_match IS NULL, skill_match DESC, id" if best_match_first else "id"
    return query(f"SELECT * FROM vacancies WHERE source='hh' AND status='queued' ORDER BY {order}")


def has_queued_hh() -> bool:
    return bool(one("SELECT 1 FROM vacancies WHERE source='hh' AND status='queued' LIMIT 1"))


def ids_where(status: str, source: str, created_since: str | None = None) -> list[int]:
    sql, args = "SELECT id FROM vacancies WHERE status=? AND source=?", [status, source]
    if created_since:
        sql += " AND created_at >= ?"
        args.append(created_since)
    return [r["id"] for r in query(sql, args)]


def titles_of_other_hh(exclude_id: int) -> list[dict]:
    return query("SELECT title, company FROM vacancies WHERE source='hh' AND id != ?", (exclude_id,))


def rejected_companies() -> list[str]:
    return [r["company"] for r in query("SELECT DISTINCT company FROM vacancies WHERE hh_state='отказ'") if r["company"]]


def known_urls(sources: list[str]) -> set[str]:
    return {r["url"] for r in query(f"SELECT url FROM vacancies WHERE source IN ({placeholders(sources)})", sources)}


def all_for_search() -> list[dict]:
    return query("SELECT id, source, title, company, status, created_at FROM vacancies ORDER BY id DESC")


def missing_letters() -> list[dict]:
    return query("SELECT * FROM vacancies WHERE source='hh' AND status='applied' AND letter_sent=0 ORDER BY id")


def approved_followups() -> list[dict]:
    return query("SELECT * FROM vacancies WHERE followup='approved' ORDER BY id")


# ---------- counters ----------
def count_by_status() -> dict[str, int]:
    return {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM vacancies GROUP BY status")}


def count(where: str, args: tuple = ()) -> int:
    """For fixed WHERE clauses written in this package only."""
    return scalar(f"SELECT COUNT(*) FROM vacancies WHERE {where}", args)


def applied_today_hh() -> int:
    return count("status='applied' AND source='hh' AND applied_at LIKE ?", (date.today().isoformat() + "%",))


def attention_since(since: str) -> int:
    return count("status='attention' AND applied_at IS NULL AND created_at >= ?", (since,))


# ---------- writing ----------
def add_manual(source: str, url: str, title: str, company: str) -> int | None:
    return insert(
        "INSERT OR IGNORE INTO vacancies(source, url, title, company, status, created_at) VALUES (?, ?, ?, ?, 'new', ?)",
        (source, url, title, company, now()),
    )


def add_found(v: dict, status: VacancyStatus, note: str | None, reasons: list[dict]) -> int | None:
    """A vacancy from a search on any site. Returns the new id, or None when it was already known."""
    return insert(
        "INSERT OR IGNORE INTO vacancies(source, ext_id, url, title, company, status, note, created_at, salary_text, "
        "salary_from, salary_to, experience, skill_match, match_info, location, country, remote, summary, contacts, "
        "company_url, skills) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (v["source"], v.get("ext_id"), v["url"], v["title"], v["company"], status, note, now(), v.get("salary_text"),
         v.get("salary_from"), v.get("salary_to"), v.get("experience"), v.get("skill_match"), _json(reasons),
         v.get("location"), v.get("country"), v.get("remote"), v.get("summary"),
         _json(v["contacts"]) if "contacts" in v else None, v.get("company_url"), v.get("skills")),
    )


def set_status(vid: int, status: VacancyStatus, reviewed: bool = False) -> None:
    ts = now()
    execute(
        "UPDATE vacancies SET status=?, applied_at=CASE WHEN ?='applied' THEN ? ELSE applied_at END, "
        "reviewed_at=CASE WHEN ? THEN ? ELSE reviewed_at END WHERE id=?",
        (status, status, ts, reviewed, ts, vid),
    )


def skip(vid: int, note: str) -> None:
    execute("UPDATE vacancies SET status='skipped', note=? WHERE id=?", (note, vid))


def delete(ids: list[int]) -> None:
    with transaction() as c:
        c.execute(f"DELETE FROM vacancies WHERE id IN ({placeholders(ids)})", ids)
        c.execute(f"DELETE FROM events WHERE vacancy_id IN ({placeholders(ids)})", ids)


def save_apply_result(vid: int, status: str, note: str | None, applied: bool, resume: str | None,
                      letter: str | None, letter_sent: bool, form: list[dict]) -> None:
    execute(
        "UPDATE vacancies SET status=?, note=?, applied_at=?, resume=?, letter_sent=?, letter=?, "
        "form_answers=COALESCE(?, form_answers) WHERE id=?",
        (status, note, now() if applied else None, resume if applied else None,
         int(letter_sent) if applied else None, letter if applied and letter_sent else None,
         _json(form) if form else None, vid),
    )


def set_hh_state(vid: int, state: str) -> int:
    ts = now()
    return execute(
        "UPDATE vacancies SET status='applied', hh_state=?, hh_state_at=?, "
        "invited_at=CASE WHEN invited_at IS NULL AND ? THEN ? ELSE invited_at END WHERE id=?",
        (state, ts, state in INVITE_STATES, ts, vid),
    )


def add_external_response(ext_id: str, url: str, title: str, company: str, date_text: str, state: str) -> int | None:
    """A response made on hh by hand. applied_at stays empty: the real date is only known as text,
    and it must not eat today's limit."""
    ts = now()
    return insert(
        "INSERT OR IGNORE INTO vacancies(source, ext_id, url, title, company, status, note, hh_state, hh_state_at, "
        "invited_at, created_at) VALUES ('hh', ?, ?, ?, ?, 'applied', ?, ?, ?, ?, ?)",
        (ext_id, url, title, company, f"отклик сделан вне бота ({date_text})", state, ts,
         ts if state in INVITE_STATES else None, ts),
    )


def mark_letter_sent(vid: int, letter: str) -> None:
    execute("UPDATE vacancies SET letter_sent=1, letter=? WHERE id=?", (letter, vid))


def set_followup(vid: int, state: str, text: str | None = None) -> None:
    if text is not None:
        execute("UPDATE vacancies SET followup=?, followup_text=? WHERE id=?", (state, text, vid))
    else:
        execute("UPDATE vacancies SET followup=?, followup_at=? WHERE id=?", (state, now(), vid))


# ---------- pipeline ----------
def ensure_stages() -> None:
    """Every sent response gets a stage; the stage is derived from hh until you move the card yourself."""
    execute(
        f"UPDATE vacancies SET stage={_SQL_STAGE_FROM_HH}, stage_at=COALESCE(hh_state_at, applied_at, created_at) "
        "WHERE status='applied' AND stage IS NULL"
    )


def set_stage(vid: int, stage: Stage, manual: bool) -> None:
    if manual:
        execute("UPDATE vacancies SET stage=?, stage_manual=1, stage_at=? WHERE id=?", (stage, now(), vid))
    else:
        execute("UPDATE vacancies SET stage=?, stage_at=? WHERE id=?", (stage, now(), vid))


def set_notes(vid: int, notes: str | None) -> None:
    execute("UPDATE vacancies SET notes=? WHERE id=?", (notes, vid))


def set_next_step(vid: int, step: str, at: str | None) -> None:
    """A new date means new reminders."""
    execute("UPDATE vacancies SET next_step=?, next_at=?, remind_day=0, remind_hour=0 WHERE id=?", (step, at, vid))


def pipeline_cards() -> list[dict]:
    return query(
        "SELECT id, source, url, title, company, stage, stage_manual, stage_at, notes, next_step, next_at, "
        "hh_state, applied_at, created_at, followup FROM vacancies WHERE status='applied' "
        "ORDER BY COALESCE(next_at, '9999'), COALESCE(stage_at, applied_at, created_at) DESC"
    )


def followup_candidates(sent_before: str, limit: int = 30) -> list[dict]:
    return query(
        "SELECT id, title, company, url, stage, COALESCE(applied_at, created_at) sent FROM vacancies "
        "WHERE status='applied' AND source='hh' AND stage IN ('applied','viewed') AND followup IS NULL "
        "AND COALESCE(applied_at, created_at) <= ? ORDER BY sent LIMIT ?",
        (sent_before, limit),
    )


def planned_steps(until: str | None = None) -> list[dict]:
    sql = ("SELECT id, title, company, stage, next_step, next_at, remind_day, remind_hour FROM vacancies "
           "WHERE next_at IS NOT NULL AND COALESCE(stage, '') != 'declined'")
    if until:
        return query(sql + " AND next_at <= ? ORDER BY next_at", (until,))
    return query(sql + " ORDER BY next_at")


def mark_reminded(vid: int, hour: bool) -> None:
    if hour:
        execute("UPDATE vacancies SET remind_hour=1, remind_day=1 WHERE id=?", (vid,))
    else:
        execute("UPDATE vacancies SET remind_day=1 WHERE id=?", (vid,))


def queue(ids: list[int]) -> None:
    execute(f"UPDATE vacancies SET status='queued' WHERE id IN ({placeholders(ids)})", ids)


