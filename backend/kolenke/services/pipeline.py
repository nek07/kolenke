"""After the response: pipeline stages, notes, next steps, reminders and follow-ups."""
from collections.abc import Callable
from datetime import datetime, timedelta

from kolenke.db.repositories import events, settings, vacancies
from kolenke.db.repositories.vacancies import HH_TO_STAGE
from kolenke.schemas.enums import STAGE_LABELS, Stage

PROGRESS = [Stage.applied, Stage.viewed, Stage.invited, Stage.interview, Stage.offer]

ensure_stages = vacancies.ensure_stages


class NotFound(LookupError):
    pass


def advance_from_hh(vid: int, hh_state: str) -> None:
    """Called by the hh sync. Moves the card forward only; a stage you set by hand is never pulled back."""
    new = HH_TO_STAGE.get(hh_state)
    v = vacancies.get(vid)
    if not new or not v:
        return
    cur, manual = Stage(v["stage"] or Stage.applied), v["stage_manual"]
    if new == Stage.declined:
        move = not manual and cur != Stage.declined
    else:
        move = (cur == Stage.declined and not manual) or (cur in PROGRESS and PROGRESS.index(new) > PROGRESS.index(cur))
    if move:
        vacancies.set_stage(vid, new, manual=False)
        events.add(vid, "stage", f"Этап: {STAGE_LABELS[new]} (по данным hh)")


def update(vid: int, changes: dict) -> dict:
    """changes holds only the fields you edited: stage, notes, next_step, next_at.
    Raises NotFound, or ValueError for a bad date."""
    v = vacancies.get(vid)
    if not v:
        raise NotFound(vid)
    stage = changes.get("stage")
    if stage and stage != v["stage"]:
        vacancies.set_stage(vid, Stage(stage), manual=True)
        events.add(vid, "stage", f"Этап: {STAGE_LABELS[Stage(stage)]}")
    if "notes" in changes and (changes["notes"] or "") != (v["notes"] or ""):
        vacancies.set_notes(vid, changes["notes"])
    if "next_step" in changes or "next_at" in changes:
        step = (changes.get("next_step", v["next_step"]) or "").strip()
        at = (changes.get("next_at", v["next_at"]) or "").strip() or None
        if at:
            try:
                at = datetime.fromisoformat(at).isoformat(timespec="seconds")
            except ValueError:
                raise ValueError("Неверная дата следующего шага") from None
        if step != (v["next_step"] or "") or at != v["next_at"]:
            vacancies.set_next_step(vid, step, at)
            if step or at:
                when = datetime.fromisoformat(at).strftime("%d.%m %H:%M") if at else "без даты"
                events.add(vid, "plan", f"Следующий шаг: {step or 'без названия'}, {when}")
    return vacancies.get(vid)


def followup_candidates() -> list[dict]:
    """Responses with no reaction for N days: a good moment to remind about yourself."""
    days = settings.get().followup_days
    return vacancies.followup_candidates((datetime.now() - timedelta(days=days)).isoformat(timespec="seconds"))


def reminders() -> dict:
    ensure_stages()
    now = datetime.now()
    planned = vacancies.planned_steps(until=(now + timedelta(days=14)).isoformat(timespec="seconds"))
    nowiso = now.isoformat(timespec="seconds")
    return {
        "upcoming": [p for p in planned if p["next_at"] >= nowiso],
        # a planned step that already passed: ask how it went
        "past": [p for p in planned if p["next_at"] < nowiso],
        "followups": followup_candidates(),
    }


def due_today_count() -> int:
    r = reminders()
    today_end = datetime.now().replace(hour=23, minute=59).isoformat(timespec="seconds")
    return len(r["followups"]) + len(r["past"]) + sum(1 for u in r["upcoming"] if u["next_at"] <= today_end)


def notify_due(notify: Callable[[str], None]) -> None:
    """Notifications a day and an hour before a planned step. Called by the scheduler."""
    now = datetime.now()
    for v in vacancies.planned_steps():
        try:
            at = datetime.fromisoformat(v["next_at"])
        except ValueError:
            continue
        left = at - now
        what = f"{v['next_step'] or 'Следующий шаг'}: {v['company']}"
        if timedelta(0) < left <= timedelta(hours=1) and not v["remind_hour"]:
            notify(f"Через {max(1, int(left.total_seconds() // 60))} мин — {what}")
            vacancies.mark_reminded(v["id"], hour=True)
        elif timedelta(hours=1) < left <= timedelta(hours=24) and not v["remind_day"]:
            day = "Сегодня" if at.date() == now.date() else "Завтра"
            notify(f"{day} в {at.strftime('%H:%M')} — {what}")
            vacancies.mark_reminded(v["id"], hour=False)
