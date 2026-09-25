"""Pure logic: salary parsing, filters, settings, answer base, chat classification, templates, limits, migrations."""
import threading
import time
from datetime import date, datetime, timedelta

import pytest
from conftest import BACKEND, add_vacancy

from kolenke import db
from kolenke.db import migrations
from kolenke.db.connection import execute, query, scalar
from kolenke.db.repositories import settings, vacancies
from kolenke.schemas.settings import AppSettings
from kolenke.services import answers, filters
from kolenke.services.text import fill, norm
from kolenke.sources.hh import chats
from kolenke.workers import scheduler
from kolenke.workers.runner import JobRunner


# ---------- salary ----------
@pytest.mark.parametrize("text, expected", [
    ("от 300 000 до 500 000 ₸ за месяц, на руки", (300000, 500000)),
    ("300 000 – 450 000 ₸", (300000, 450000)),
    ("от 150 000 ₽ за месяц", (150000, None)),
    ("до 1 000 $", (None, 1000)),
    ("300 000 ₸ за месяц, до вычета налогов", (300000, None)),  # fixed salary, «до» belongs to the tax note
    ("от 250 000 ₸ до вычета налогов", (250000, None)),
    ("", (None, None)),
    (None, (None, None)),
    ("з/п по договорённости", (None, None)),
    ("от\xa0400\xa0000\xa0₸", (400000, None)),
    ("от 400 000 ₸", (400000, None)),  # hh puts a narrow no-break space between thousands
])
def test_parse_salary(text, expected):
    assert filters.parse_salary(text) == expected


# ---------- filters ----------
def s_with(**over) -> AppSettings:
    return settings.get().model_copy(update=over)


def test_filter_passes_by_default():
    ok, note, reasons = filters.check({"title": "Backend", "company": "Kaspi"}, s_with(), set())
    assert ok and note is None
    assert all(r["ok"] for r in reasons)


def test_filter_excluded_word_and_first_reason_is_note():
    ok, note, _ = filters.check({"title": "Senior Backend", "company": "X"}, s_with(hh_exclude="senior, lead"), set())
    assert not ok and "senior" in note


def test_filter_salary_floor():
    v = {"title": "Dev", "company": "X", "salary_from": 200000, "salary_to": 300000, "salary_text": "200–300 тыс"}
    assert not filters.check(v, s_with(f_salary_min=400000), set())[0]
    assert filters.check(v, s_with(f_salary_min=250000), set())[0]  # upper bound counts


def test_filter_no_salary():
    v = {"title": "Dev", "company": "X"}
    assert not filters.check(v, s_with(f_skip_no_salary=True), set())[0]
    assert filters.check(v, s_with(f_skip_no_salary=False, f_salary_min=300000), set())[0]  # kept, just explained


def test_filter_company_blacklist_and_rejected():
    v = {"title": "Dev", "company": "АО «Kaspi Bank»"}
    assert not filters.check(v, s_with(f_exclude_companies="kaspi\nhalyk"), set())[0]
    assert not filters.check(v, s_with(f_skip_rejected=True), {norm("АО «Kaspi Bank»")})[0]
    assert filters.check(v, s_with(f_skip_rejected=False), {norm("АО «Kaspi Bank»")})[0]


def test_filter_skill_match():
    assert not filters.check({"title": "D", "company": "X", "skill_match": 30}, s_with(f_min_match=50), set())[0]
    assert filters.check({"title": "D", "company": "X", "skill_match": 70}, s_with(f_min_match=50), set())[0]
    assert filters.check({"title": "D", "company": "X", "skill_match": None}, s_with(f_min_match=50), set())[0]


def test_rejected_companies_from_db():
    add_vacancy(ext_id="1", company="ТОО Рога", hh_state="отказ", status="applied")
    add_vacancy(ext_id="2", company="ТОО Копыта", hh_state="просмотрен", status="applied")
    assert filters.rejected_companies() == {norm("ТОО Рога")}


# ---------- settings storage ----------
@pytest.mark.parametrize("raw, expected", [
    ("80", 80), ("", 50), ("abc", 50), ("0", 1), ("-5", 1), ("7.9", 7), ("1 000", 50),
])
def test_stored_limits_are_read_safely(raw, expected):
    """Values saved by older versions as free text: garbage falls back to the default (50), numbers are clamped."""
    assert AppSettings.from_storage({"hh_daily_limit": raw}).hh_daily_limit == expected


def test_stored_values_of_every_kind():
    s = AppSettings.from_storage({
        "autopilot_to": "99", "f_salary_min": "400 000", "f_skip_rejected": "0", "f_experience": "noExperience,bogus",
        "hh_resumes": '[{"hash": "a1", "title": "Аналитик"}]', "hh_resume_hash": "a1", "autopilot_mode": "yolo",
    })
    assert (s.autopilot_to, s.f_salary_min, s.f_skip_rejected) == (24, 400000, False)
    assert s.f_experience == ["noExperience"] and s.resume_title == "Аналитик" and s.autopilot_mode == "review"


def test_settings_round_trip_through_storage():
    settings.save({"f_experience": ["between1And3", "moreThan6"], "f_sort_match": False, "f_salary_min": 500000})
    raw = {r["key"]: r["value"] for r in query("SELECT key, value FROM settings")}
    assert raw["f_experience"] == "between1And3,moreThan6" and raw["f_sort_match"] == "0" and raw["f_salary_min"] == "500000"
    s = settings.get()
    assert s.f_experience == ["between1And3", "moreThan6"] and not s.f_sort_match and s.f_salary_min == 500000


# ---------- answer base ----------
def fill_answer(topic, text):
    execute("UPDATE answers SET answer=? WHERE topic=?", (text, topic))


def test_answer_match_and_narrow_topic_wins():
    fill_answer("Зарплатные ожидания", "от 800 000 ₸")
    assert answers.match("Ваши зарплатные ожидания?") == ("Зарплатные ожидания", "от 800 000 ₸")
    assert answers.match("Опишите ваш опыт работы с SQL")[0] == "SQL"
    assert answers.match("Сколько лет опыта в Python?")[0] == "Опыт работы"
    assert answers.match("Вы работали официально? Готовы подтвердить опыт?")[0] == "Официальное трудоустройство"


def test_answer_unknown_and_empty():
    assert answers.match("Как зовут вашу кошку?") == (None, "")
    assert answers.match("Ваш уровень английского?") == ("Английский", "")  # topic found, answer not filled


def test_remember_unknown_counts_repeats():
    answers.remember_unknown("Есть ли у вас машина?", "form")
    answers.remember_unknown("Есть ли у вас машина?", "chat")
    assert query("SELECT text, seen FROM questions") == [{"text": "Есть ли у вас машина?", "seen": 2}]


# ---------- chats ----------
def m(text, own=False, system=False, author=""):
    return {"id": str(hash(text)), "text": text, "own": own, "system": system, "author": author}


def test_robot_active_join_and_leave():
    msgs = [m("Без сопроводительного письма", own=True), m("Пользователь Робот-рекрутер присоединился к чату", system=True),
            m("Ваши зарплатные ожидания?", author="Робот-рекрутер")]
    assert chats.robot_active(msgs)
    assert not chats.robot_active(msgs + [m("Пользователь Робот-рекрутер покинул чат", system=True)])


def test_pending_incoming_after_last_own_message():
    msgs = [m("Вопрос 1?"), m("Ответ", own=True), m("Пользователь Робот-рекрутер покинул чат", system=True), m("Вопрос 2?")]
    assert [x["text"] for x in chats.pending_incoming(msgs)] == ["Вопрос 2?"]


@pytest.mark.parametrize("text, robot, expected", [
    ("Ваши зарплатные ожидания?", True, True),
    ("Спасибо! Ваши ответы отправлены работодателю.", True, False),
    ("Компания рассмотрит ваше резюме и позже свяжется", False, False),
    ("Здравствуйте! Благодарим вас за отклик. К сожалению…", False, False),
    ("Приглашаем вас на собеседование завтра в 15:00", False, True),  # live person, no «?», still needs you
    ("Вакансия не прошла проверку и была удалена", False, False),
])
def test_needs_reply(text, robot, expected):
    assert chats.needs_reply(text, robot) is expected


def test_clean_text_drops_invisible_padding():
    assert chats.clean_text("Добрый\xa0день​!\n\n\n\nЖдём") == "Добрый день !\n\nЖдём"


def test_notify_passes_text_as_data_not_code(notifications, monkeypatch):
    """Company names come from hh: they must never become AppleScript code."""
    from kolenke.services import notify
    calls = []
    monkeypatch.setattr(notify, "_osascript", calls.append)
    evil = 'ТОО X" & (do shell script "touch /tmp/pwned") & "'
    notify.notify(evil)
    args = calls[0]
    scripts = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
    assert all(evil not in sc and "do shell script" not in sc for sc in scripts)
    assert args[-1] == evil


def test_reply_to_closed_chat_is_dropped_not_retried(monkeypatch):
    """hh closes the chat after a refusal: the approved reply must not fail every autopilot cycle forever."""
    execute("INSERT INTO chat_items(chat_id, msg_id, company, message, reply, status, created_at) VALUES "
            "('c1', 'm1', 'Andersen', 'Отказ', 'Спасибо', 'approved', '')")
    page = type("P", (), {"goto": lambda self, *a, **k: None, "wait_for_timeout": lambda self, ms: None})()
    monkeypatch.setattr(chats, "read_chat", lambda page: {"messages": []})
    monkeypatch.setattr(chats, "can_write", lambda page: False)
    chats.send_approved(page, "hh.kz")
    assert query("SELECT status FROM chat_items WHERE msg_id='m1'")[0]["status"] == "closed"


# ---------- templates, limits, tasks ----------
def test_fill_template_and_position_fallback():
    settings.save({"full_name": "Аня", "phone": "+7 700", "desired_position": "Аналитик"})
    s = settings.get()
    assert fill("{name} {phone}: {position} в {company}", s, "Kaspi", "") == "Аня +7 700: Аналитик в Kaspi"
    assert fill("{position}", s, position="DevOps") == "DevOps"


def test_applied_today_counts_only_hh():
    add_vacancy(ext_id="1", status="applied", applied_at=db.now())
    add_vacancy(ext_id="2", source="other", url="https://bank.kz/job", status="applied", applied_at=db.now())
    add_vacancy(ext_id="3", status="applied", applied_at=(date.today() - timedelta(days=1)).isoformat() + "T10:00:00")
    assert vacancies.applied_today_hh() == 1


def test_job_runs_one_task_at_a_time():
    j, gate, started = JobRunner(), threading.Event(), []

    def fn():
        started.append(1)
        gate.wait(2)

    results = []
    threads = [threading.Thread(target=lambda: results.append(j.start("t", fn))) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1
    gate.set()
    time.sleep(0.1)
    assert len(started) == 1 and not j.running


def test_job_error_is_logged_not_raised():
    j = JobRunner()
    j.start("падающая задача", lambda: 1 / 0)
    time.sleep(0.2)
    assert "падающая задача" in query("SELECT msg FROM log ORDER BY id DESC LIMIT 1")[0]["msg"]


def test_stop_ends_a_pause_early():
    j = JobRunner()
    threading.Timer(0.1, j.stop).start()
    t = time.monotonic()
    j.sleep(5)
    assert time.monotonic() - t < 2


def test_scheduler_starts_the_autopilot_only_in_its_hours(monkeypatch):
    started = []
    monkeypatch.setattr(scheduler.runner, "start", lambda name, fn: started.append(name) or True)
    scheduler.state.next_run = None
    settings.save({"autopilot_on": True, "autopilot_from": 8, "autopilot_to": 22, "autopilot_interval": 30})
    scheduler.tick(datetime(2030, 1, 1, 7, 0))
    assert started == []
    scheduler.tick(datetime(2030, 1, 1, 9, 0))
    scheduler.tick(datetime(2030, 1, 1, 9, 10))  # the next run is at 9:30
    assert started == ["Автопилот"] and scheduler.state.next_run == datetime(2030, 1, 1, 9, 30)
    settings.save({"autopilot_on": False})
    scheduler.tick(datetime(2030, 1, 1, 10, 0))
    assert scheduler.state.next_run is None


# ---------- database ----------
def test_migrate_is_idempotent_and_versioned():
    v = db.init()
    assert db.init() == v == len(migrations.MIGRATIONS)
    assert scalar("SELECT COUNT(*) FROM answers") == len(migrations.DEFAULT_ANSWERS)


def test_migrate_upgrades_an_old_database(tmp_path, monkeypatch):
    """A database from before versioning (user_version 0, fewer columns) keeps its rows and gains the new columns."""
    import sqlite3

    from kolenke.config import get_config
    old = tmp_path / "jobbot.db"
    c = sqlite3.connect(old)
    c.executescript("CREATE TABLE vacancies (id INTEGER PRIMARY KEY, source TEXT, ext_id TEXT, url TEXT UNIQUE, title TEXT, "
                    "company TEXT, status TEXT, note TEXT, created_at TEXT, applied_at TEXT, hh_state TEXT, hh_state_at TEXT);"
                    "INSERT INTO vacancies(source, url, title, status, hh_state, hh_state_at) "
                    "VALUES ('hh', 'https://hh.kz/vacancy/1', 'Old', 'applied', 'приглашение', '2025-01-01T10:00:00');")
    c.close()
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    assert db.init() == len(migrations.MIGRATIONS)
    row = query("SELECT title, invited_at, stage FROM vacancies")[0]
    assert row == {"title": "Old", "invited_at": "2025-01-01T10:00:00", "stage": None}


# ---------- guard rails ----------
def test_code_never_opens_the_one_click_response_url():
    """hh sends a response just by opening /applicant/vacancy_response?vacancyId=…: the bot must only ever click
    «Откликнуться» on the vacancy page, where the questionnaire and letter are handled."""
    files = list((BACKEND / "kolenke").rglob("*.py"))
    assert files
    for f in files:
        assert "vacancy_response?" not in f.read_text(), f.name


def test_api_layer_does_not_import_the_browser():
    """The API must start without Playwright: browser code is loaded only when a task runs."""
    import subprocess
    import sys
    code = "import sys, kolenke.main; print('playwright' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=BACKEND)
    assert out.stdout.strip() == "False", out.stderr
