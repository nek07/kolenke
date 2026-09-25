"""Vacancy actions you take in the page, and the history panel of one vacancy."""
import json

from kolenke.db.repositories import chats, events, vacancies
from kolenke.schemas.enums import VacancyStatus
from kolenke.services.text import norm

STATUS_EVENTS = {
    VacancyStatus.queued: "Вы добавили в очередь на отклик",
    VacancyStatus.skipped: "Вы пропустили",
    VacancyStatus.new: "Вы вернули в новые",
    VacancyStatus.applied: "Вы отметили: откликнулись",
    VacancyStatus.attention: "Отмечена как требующая ответа",
}
REVIEW_EVENTS = {
    VacancyStatus.queued: "Вы одобрили при проверке: «Откликнуться»",
    VacancyStatus.skipped: "Вы пропустили при проверке",
}


def set_status(ids: list[int], status: VacancyStatus, review: bool = False) -> None:
    for vid in ids:
        vacancies.set_status(vid, status, reviewed=review)
        events.add(vid, status, (REVIEW_EVENTS.get(status) if review else None) or STATUS_EVENTS[status])


def queue_all_new(source: str) -> int:
    ids = vacancies.ids_where(VacancyStatus.new, source)
    if ids:
        vacancies.queue(ids)
    for vid in ids:
        events.add(vid, "queued", "Вы добавили в очередь («Все новые в очередь»)")
    return len(ids)


def detail(vid: int) -> dict | None:
    """The vacancy with its history, questionnaire answers and the employer chats that belong to it."""
    v = vacancies.get(vid)
    if not v:
        return None
    return {
        **v,
        "match_info": json.loads(v["match_info"] or "[]"),
        "form_answers": json.loads(v["form_answers"] or "[]"),
        "contacts": json.loads(v["contacts"]) if v["contacts"] else None,
        "events": events.for_vacancy(vid),
        "chats": _chats_of(v),
    }


def _chats_of(v: dict) -> list[dict]:
    """Chats keep the company and (not always) the vacancy title: match the company, and when the chat names
    another known vacancy of this company, it belongs to that one."""
    words = [w for w in norm(v["company"]).split() if len(w) > 3 and w not in ("тоо", "филиал")]

    def same_company(company):
        return bool(words) and any(w in norm(company) for w in words)

    title = norm(v["title"])
    siblings = {norm(r["title"]) for r in vacancies.titles_of_other_hh(v["id"]) if same_company(r["company"])} - {title}

    def belongs(c):
        if c["vacancy"] == v["title"]:
            return True
        if not same_company(c["company"]) or norm(c["vacancy"]) in siblings:
            return False
        if title in norm(c["message"]):
            return True
        return not siblings  # the chat doesn't say which vacancy: only safe when it is the company's only one

    return [c for c in chats.visible() if belongs(c)]
