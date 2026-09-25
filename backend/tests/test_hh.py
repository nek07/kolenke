"""hh logic around the browser: how a response, the employer reaction and an autopilot cycle end up in the database.
The browser itself is not started: the page steps are replaced, the bookkeeping is real."""
from conftest import add_vacancy

from kolenke.db.connection import now, query
from kolenke.db.repositories import settings
from kolenke.schemas.enums import VacancyStatus
from kolenke.sources.hh import apply, responses
from kolenke.workers import autopilot


def events_of(vid):
    return [(e["kind"], e["text"]) for e in query("SELECT kind, text FROM events WHERE vacancy_id=? ORDER BY id", (vid,))]


def test_applied_with_letter_and_questionnaire_is_recorded():
    v = add_vacancy(status="queued")
    info = {"letter": True, "letter_via": "form", "resume": "Аналитик", "form": [{"q": "Опыт?", "a": "3 года"}]}
    apply._record(query("SELECT * FROM vacancies WHERE id=?", (v,))[0], VacancyStatus.applied, None, info, "Письмо")
    row = query("SELECT status, applied_at, resume, letter_sent, letter, form_answers FROM vacancies WHERE id=?", (v,))[0]
    assert row["status"] == "applied" and row["applied_at"] and row["resume"] == "Аналитик"
    assert row["letter_sent"] == 1 and row["letter"] == "Письмо" and "3 года" in row["form_answers"]
    assert [k for k, _ in events_of(v)] == ["applied", "form", "letter"]


def test_already_applied_does_not_count_as_new_response():
    v = add_vacancy(status="queued")
    apply._record(query("SELECT * FROM vacancies WHERE id=?", (v,))[0], VacancyStatus.applied, apply.ALREADY_APPLIED,
                  {"letter": False, "letter_via": None, "resume": None, "form": []}, "Письмо")
    row = query("SELECT status, applied_at FROM vacancies WHERE id=?", (v,))[0]
    assert row == {"status": "applied", "applied_at": None}  # not in today's limit
    assert events_of(v) == [("applied", "Отклик уже был сделан раньше")]


def test_questionnaire_without_answers_needs_you():
    v = add_vacancy(status="queued")
    apply._record(query("SELECT * FROM vacancies WHERE id=?", (v,))[0], VacancyStatus.attention, "анкета, нет ответа на: Машина?",
                  {"letter": False, "letter_via": None, "resume": None, "form": []}, "")
    assert query("SELECT status FROM vacancies WHERE id=?", (v,))[0]["status"] == "attention"
    assert events_of(v)[0][0] == "attention"


def test_sync_updates_known_and_adds_manual_responses():
    known = add_vacancy(ext_id="100", status="applied", applied_at=now(), hh_state="не просмотрен")
    u, a = responses._store("hh.kz", {"href": "https://hh.kz/vacancy/100", "state": "invitation", "state_text": "", "title": "", "company": "", "date": ""})
    assert (u, a) == (1, 0)
    row = query("SELECT hh_state, invited_at, stage FROM vacancies WHERE id=?", (known,))[0]
    assert row["hh_state"] == "приглашение" and row["invited_at"] and row["stage"] == "invited"

    u, a = responses._store("hh.kz", {"href": "https://hh.kz/vacancy/200", "state": "discard", "state_text": "",
                                      "title": "QA", "company": "Kaspi", "date": "12 марта"})
    assert (u, a) == (0, 1)
    manual = query("SELECT * FROM vacancies WHERE ext_id='200'")[0]
    assert manual["status"] == "applied" and manual["applied_at"] is None and manual["hh_state"] == "отказ"
    assert manual["stage"] == "declined"


def test_autopilot_review_mode_waits_for_you(monkeypatch, notifications):
    settings.save({"autopilot_mode": "review", "other_monitor": False})
    monkeypatch.setattr(autopilot, "search", lambda fresh: add_vacancy(ext_id="1"))
    monkeypatch.setattr(autopilot, "apply_queue", lambda: (_ for _ in ()).throw(AssertionError("must not apply")))
    monkeypatch.setattr(autopilot.chats, "run", lambda: None)
    autopilot.cycle()
    assert query("SELECT status FROM vacancies")[0]["status"] == "new"
    assert notifications and "Пролистайте" in notifications[0]


def test_autopilot_auto_mode_queues_and_applies(monkeypatch):
    settings.save({"autopilot_mode": "auto", "other_monitor": False})
    applied = []
    monkeypatch.setattr(autopilot, "search", lambda fresh: add_vacancy(ext_id="1"))
    monkeypatch.setattr(autopilot, "apply_queue", lambda: applied.append([r["status"] for r in query("SELECT status FROM vacancies")]))
    monkeypatch.setattr(autopilot.chats, "run", lambda: None)
    autopilot.cycle()
    assert applied == [["queued"]]
