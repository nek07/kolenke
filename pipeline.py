"""After the response: pipeline stages, notes, next steps, reminders and follow-ups."""
from datetime import datetime, timedelta

import db

STAGES = ["applied", "viewed", "invited", "interview", "offer", "declined"]
PROGRESS = ["applied", "viewed", "invited", "interview", "offer"]
LABELS = {
    "applied": "Отклик", "viewed": "Просмотрен", "invited": "Приглашение",
    "interview": "Собеседование", "offer": "Оффер", "declined": "Не сейчас",
}
FROM_HH = {
    "не просмотрен": "applied", "просмотрен": "viewed", "приглашение": "invited",
    "собеседование": "interview", "выход на работу": "offer", "отказ": "declined",
}
_SQL_FROM_HH = "CASE hh_state " + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in FROM_HH.items()) + " ELSE 'applied' END"


def ensure_stages():
    """Every sent response gets a stage; the stage is derived from hh until you move the card yourself."""
    db.x(
        f"UPDATE vacancies SET stage={_SQL_FROM_HH}, stage_at=COALESCE(hh_state_at, applied_at, created_at) "
        "WHERE status='applied' AND stage IS NULL"
    )


def advance_from_hh(vid, hh_state):
    """Called by the hh sync. Moves the card forward only; a stage you set by hand is never pulled back."""
    new = FROM_HH.get(hh_state)
    rows = db.q("SELECT stage, stage_manual FROM vacancies WHERE id=?", (vid,))
    if not new or not rows:
        return
    cur, manual = rows[0]["stage"] or "applied", rows[0]["stage_manual"]
    if new == "declined":
        move = not manual and cur != "declined"
    else:
        move = cur == "declined" and not manual or (cur in PROGRESS and PROGRESS.index(new) > PROGRESS.index(cur))
    if move:
        db.x("UPDATE vacancies SET stage=?, stage_at=? WHERE id=?", (new, db.now(), vid))
        db.event(vid, "stage", f"Этап: {LABELS[new]} (по данным hh)")


def update(vid, data: dict):
    rows = db.q("SELECT * FROM vacancies WHERE id=?", (vid,))
    if not rows:
        return None
    v = rows[0]
    if data.get("stage") in STAGES and data["stage"] != v["stage"]:
        db.x("UPDATE vacancies SET stage=?, stage_manual=1, stage_at=? WHERE id=?", (data["stage"], db.now(), vid))
        db.event(vid, "stage", f"Этап: {LABELS[data['stage']]}")
    if "notes" in data and (data["notes"] or "") != (v["notes"] or ""):
        db.x("UPDATE vacancies SET notes=? WHERE id=?", (data["notes"], vid))
    if "next_step" in data or "next_at" in data:
        step = (data.get("next_step", v["next_step"]) or "").strip()
        at = (data.get("next_at", v["next_at"]) or "").strip() or None
        if at:
            try:
                at = datetime.fromisoformat(at).isoformat(timespec="seconds")
            except ValueError:
                raise ValueError("Неверная дата следующего шага")
        if step != (v["next_step"] or "") or at != v["next_at"]:
            # a new date means new reminders
            db.x("UPDATE vacancies SET next_step=?, next_at=?, remind_day=0, remind_hour=0 WHERE id=?", (step, at, vid))
            if step or at:
                when = datetime.fromisoformat(at).strftime("%d.%m %H:%M") if at else "без даты"
                db.event(vid, "plan", f"Следующий шаг: {step or 'без названия'}, {when}")
    return db.q("SELECT * FROM vacancies WHERE id=?", (vid,))[0]


def followup_candidates():
    """Responses with no reaction for N days: a good moment to remind about yourself."""
    days = int(db.get_settings()["followup_days"] or 5)
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    return db.q(
        "SELECT id, title, company, url, stage, COALESCE(applied_at, created_at) sent FROM vacancies "
        "WHERE status='applied' AND source='hh' AND stage IN ('applied','viewed') AND followup IS NULL "
        "AND COALESCE(applied_at, created_at) <= ? ORDER BY sent LIMIT 30",
        (since,),
    )


def reminders():
    ensure_stages()
    now = datetime.now()
    soon = (now + timedelta(days=14)).isoformat(timespec="seconds")
    planned = db.q(
        "SELECT id, title, company, stage, next_step, next_at FROM vacancies "
        "WHERE next_at IS NOT NULL AND next_at <= ? AND COALESCE(stage, '') != 'declined' ORDER BY next_at",
        (soon,),
    )
    nowiso = now.isoformat(timespec="seconds")
    return {
        "upcoming": [p for p in planned if p["next_at"] >= nowiso],
        # a planned step that already passed: ask how it went
        "past": [p for p in planned if p["next_at"] < nowiso],
        "followups": followup_candidates(),
    }


def notify_due(notify):
    """Mac notifications a day and an hour before a planned step. Called by the background loop."""
    now = datetime.now()
    for v in db.q("SELECT id, title, company, next_step, next_at, remind_day, remind_hour FROM vacancies "
                  "WHERE next_at IS NOT NULL AND COALESCE(stage, '') != 'declined'"):
        try:
            at = datetime.fromisoformat(v["next_at"])
        except ValueError:
            continue
        left = at - now
        what = f"{v['next_step'] or 'Следующий шаг'}: {v['company']}"
        if timedelta(0) < left <= timedelta(hours=1) and not v["remind_hour"]:
            notify(f"Через {max(1, int(left.total_seconds() // 60))} мин — {what}")
            db.x("UPDATE vacancies SET remind_hour=1, remind_day=1 WHERE id=?", (v["id"],))
        elif timedelta(hours=1) < left <= timedelta(hours=24) and not v["remind_day"]:
            day = "Сегодня" if at.date() == now.date() else "Завтра"
            notify(f"{day} в {at.strftime('%H:%M')} — {what}")
            db.x("UPDATE vacancies SET remind_day=1 WHERE id=?", (v["id"],))
