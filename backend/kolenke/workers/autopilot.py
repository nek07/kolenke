"""Autopilot cycle: find fresh vacancies for the resume, then either apply at once (auto) or notify and let you
swipe through them (review), check the other boards and handle hh chats."""
from kolenke.db.connection import now
from kolenke.db.repositories import events, settings, vacancies
from kolenke.db.repositories.events import log
from kolenke.schemas.enums import AutopilotMode, VacancyStatus
from kolenke.services.notify import notify
from kolenke.sources.boards.monitor import monitor
from kolenke.sources.hh import chats
from kolenke.sources.hh.apply import apply_queue
from kolenke.sources.hh.search import search
from kolenke.workers.runner import runner


def cycle() -> None:
    started = now()
    review = settings.get().autopilot_mode != AutopilotMode.auto
    if review and vacancies.has_queued_hh():
        log("Автопилот: откликаюсь на вакансии, которые вы одобрили")
        apply_queue()  # what you approved in the review since the last cycle
    if runner.stop_requested:
        return
    search(fresh=True)
    if runner.stop_requested:
        return
    fresh = vacancies.ids_where(VacancyStatus.new, "hh", created_since=started)
    if not fresh:
        log("Автопилот: новых вакансий нет")
    elif review:
        log(f"Автопилот: {len(fresh)} новых подходящих вакансий ждут вашей проверки")
        notify(f"{len(fresh)} новых подходящих вакансий. Пролистайте их в kolenke")
    else:
        vacancies.queue(fresh)
        for vid in fresh:
            events.add(vid, "queued", "Автопилот поставил в очередь")
        log(f"Автопилот: {len(fresh)} свежих вакансий — откликаюсь")
        apply_queue()
    if not runner.stop_requested and settings.get().other_monitor:
        try:
            n = monitor()
            if n:
                notify(f"{n} новых вакансий на других сайтах. Смотрите «Другие сайты»")
        except Exception as e:
            log(f"Другие сайты: ошибка {e}")
    if not runner.stop_requested:
        try:  # a broken chat must not cancel the rest of the cycle
            chats.run()
        except Exception as e:
            log(f"Чаты: ошибка {str(e)[:120]}")
    attention = vacancies.attention_since(started)
    if attention:
        notify(f"{attention} вакансий с анкетой ждут ваших ответов")
