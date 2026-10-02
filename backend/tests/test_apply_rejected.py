"""«Уже отвечала «не сейчас»» at apply time: it stops the autopilot, never a vacancy you queued yourself."""
from contextlib import contextmanager

from conftest import add_vacancy

from kolenke.db.connection import scalar
from kolenke.db.repositories import events, settings
from kolenke.sources.hh import apply


def _run(monkeypatch, queued_text):
    settings.save({"f_skip_rejected": True, "hh_pause_min": 0, "hh_pause_max": 0})
    add_vacancy(ext_id="1", company="ТОО Dreamlab", status="applied", hh_state="отказ")  # an earlier «не сейчас»
    vid = add_vacancy(ext_id="2", url="https://hh.kz/vacancy/2", company="ТОО Dreamlab", status="queued")
    events.add(vid, "queued", queued_text)
    tried = []

    @contextmanager
    def page():
        yield (type("P", (), {"wait_for_timeout": lambda self, ms: None})(), "hh.kz")

    monkeypatch.setattr(apply, "logged_in_page", page)
    monkeypatch.setattr(apply, "apply_one", lambda page, domain, v, *a: tried.append(v["id"]) or ("applied", None, {
        "letter": False, "letter_via": None, "resume": None, "form": []}))
    apply.apply_queue()
    return vid, tried


def test_a_vacancy_you_queued_is_applied_even_after_a_refusal(monkeypatch):
    vid, tried = _run(monkeypatch, "Вы добавили в очередь на отклик")
    assert tried == [vid]
    assert scalar("SELECT status FROM vacancies WHERE id=?", (vid,)) == "applied"


def test_the_autopilot_skips_a_company_that_said_not_now(monkeypatch):
    vid, tried = _run(monkeypatch, events.AUTOPILOT_QUEUED)
    assert tried == []
    assert scalar("SELECT status FROM vacancies WHERE id=?", (vid,)) == "skipped"
    assert "не сейчас" in scalar("SELECT note FROM vacancies WHERE id=?", (vid,))
