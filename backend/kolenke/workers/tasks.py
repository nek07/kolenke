"""Tasks the page can start. The key is part of the API: POST /api/jobs/{key}."""
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    key: str
    title: str
    run: Callable[[], object]


def _lazy(module: str, name: str) -> Callable[[], object]:
    """Browser code is imported only when a task runs, so the API starts fast and tests need no Playwright."""
    def run():
        import importlib
        return getattr(importlib.import_module(module), name)()
    return run


TASKS: dict[str, Task] = {t.key: t for t in [
    Task("hh_login", "Вход в hh", _lazy("kolenke.sources.hh.session", "login")),
    Task("hh_check", "Проверка входа hh", _lazy("kolenke.sources.hh.session", "check_login")),
    Task("hh_resumes", "Загрузка резюме hh", _lazy("kolenke.sources.hh.session", "load_resumes")),
    Task("hh_search", "Поиск вакансий hh", _lazy("kolenke.sources.hh.search", "search")),
    Task("hh_apply", "Отклики hh", _lazy("kolenke.sources.hh.apply", "apply_queue")),
    Task("hh_sync", "Статусы откликов hh", _lazy("kolenke.sources.hh.responses", "sync_responses")),
    Task("hh_letters", "Письма к откликам", _lazy("kolenke.sources.hh.letters", "send_missing_letters")),
    Task("hh_followups", "Напоминания о себе", _lazy("kolenke.sources.hh.letters", "send_followups")),
    Task("other_search", "Поиск на других сайтах", _lazy("kolenke.sources.boards.monitor", "monitor")),
    Task("chat_check", "Чаты hh", _lazy("kolenke.sources.hh.chats", "run")),
    Task("autopilot_now", "Автопилот", _lazy("kolenke.workers.autopilot", "cycle")),
    Task("mail_send", "Рассылка резюме", _lazy("kolenke.services.mailer", "send_queue")),
]}
