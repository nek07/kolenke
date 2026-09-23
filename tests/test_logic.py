"""Pure logic: salary parsing, filters, answer base, chat classification, templates, limits."""
import threading
import time
from datetime import date, timedelta

import pytest

import answers
import chat_bot
import db
import filters
from conftest import add_vacancy
from jobs import Job


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
])
def test_parse_salary(text, expected):
    assert filters.parse_salary(text) == expected


# ---------- filters ----------
def settings(**over):
    s = db.get_settings()
    s.update(over)
    return s


def test_filter_passes_by_default():
    ok, note, reasons = filters.check({"title": "Backend", "company": "Kaspi"}, settings(), set())
    assert ok and note is None
    assert all(r["ok"] for r in reasons)


def test_filter_excluded_word_and_first_reason_is_note():
    ok, note, _ = filters.check({"title": "Senior Backend", "company": "X"}, settings(hh_exclude="senior, lead"), set())
    assert not ok and "senior" in note


def test_filter_salary_floor():
    v = {"title": "Dev", "company": "X", "salary_from": 200000, "salary_to": 300000, "salary_text": "200–300 тыс"}
    assert not filters.check(v, settings(f_salary_min="400 000"), set())[0]
    assert filters.check(v, settings(f_salary_min="250000"), set())[0]  # upper bound counts


def test_filter_no_salary():
    v = {"title": "Dev", "company": "X"}
    assert not filters.check(v, settings(f_skip_no_salary="1"), set())[0]
    assert filters.check(v, settings(f_skip_no_salary="0", f_salary_min="300000"), set())[0]  # kept, just explained


def test_filter_company_blacklist_and_rejected():
    v = {"title": "Dev", "company": "АО «Kaspi Bank»"}
    assert not filters.check(v, settings(f_exclude_companies="kaspi\nhalyk"), set())[0]
    assert not filters.check(v, settings(f_skip_rejected="1"), {filters.norm("АО «Kaspi Bank»")})[0]
    assert filters.check(v, settings(f_skip_rejected="0"), {filters.norm("АО «Kaspi Bank»")})[0]


def test_filter_skill_match():
    assert not filters.check({"title": "D", "company": "X", "skill_match": 30}, settings(f_min_match="50"), set())[0]
    assert filters.check({"title": "D", "company": "X", "skill_match": 70}, settings(f_min_match="50"), set())[0]
    assert filters.check({"title": "D", "company": "X", "skill_match": None}, settings(f_min_match="50"), set())[0]


def test_rejected_companies_from_db():
    add_vacancy(ext_id="1", company="ТОО Рога", hh_state="отказ", status="applied")
    add_vacancy(ext_id="2", company="ТОО Копыта", hh_state="просмотрен", status="applied")
    assert filters.rejected_companies() == {filters.norm("ТОО Рога")}


# ---------- answer base ----------
def fill_answer(topic, text):
    db.x("UPDATE answers SET answer=? WHERE topic=?", (text, topic))


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
    rows = db.q("SELECT text, seen FROM questions")
    assert rows == [{"text": "Есть ли у вас машина?", "seen": 2}]


# ---------- chats ----------
def m(text, own=False, system=False, author=""):
    return {"id": str(hash(text)), "text": text, "own": own, "system": system, "author": author}


def test_robot_active_join_and_leave():
    msgs = [m("Без сопроводительного письма", own=True), m("Пользователь Робот-рекрутер присоединился к чату", system=True),
            m("Ваши зарплатные ожидания?", author="Робот-рекрутер")]
    assert chat_bot._robot_active(msgs)
    assert not chat_bot._robot_active(msgs + [m("Пользователь Робот-рекрутер покинул чат", system=True)])


def test_pending_incoming_after_last_own_message():
    msgs = [m("Вопрос 1?"), m("Ответ", own=True), m("Пользователь Робот-рекрутер покинул чат", system=True), m("Вопрос 2?")]
    assert [x["text"] for x in chat_bot._pending_incoming(msgs)] == ["Вопрос 2?"]


@pytest.mark.parametrize("text, robot, expected", [
    ("Ваши зарплатные ожидания?", True, True),
    ("Спасибо! Ваши ответы отправлены работодателю.", True, False),
    ("Компания рассмотрит ваше резюме и позже свяжется", False, False),
    ("Здравствуйте! Благодарим вас за отклик. К сожалению…", False, False),
    ("Приглашаем вас на собеседование завтра в 15:00", False, True),  # live person, no «?», still needs you
    ("Вакансия не прошла проверку и была удалена", False, False),
])
def test_needs_reply(text, robot, expected):
    assert chat_bot.needs_reply(text, robot) is expected


def test_notify_passes_text_as_data_not_code(monkeypatch):
    """Company names come from hh: they must never become AppleScript code."""
    import importlib
    importlib.reload(chat_bot)  # the fixture stubbed notify; test the real one
    calls = []
    monkeypatch.setattr(chat_bot.subprocess, "run", lambda args, **kw: calls.append(args))
    evil = 'ТОО X" & (do shell script "touch /tmp/pwned") & "'
    chat_bot.notify(evil)
    args = calls[0]
    scripts = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
    assert all(evil not in sc and "do shell script" not in sc for sc in scripts)
    assert args[-1] == evil


# ---------- templates, limits, jobs ----------
def test_fill_template_and_position_fallback():
    db.set_settings({"full_name": "Аня", "phone": "+7 700", "desired_position": "Аналитик"})
    assert db.fill("{name} {phone}: {position} в {company}", company="Kaspi", position="") == "Аня +7 700: Аналитик в Kaspi"
    assert db.fill("{position}", position="DevOps") == "DevOps"


def test_count_today_only_hh_counts_for_the_hh_limit():
    add_vacancy(ext_id="1", status="applied", applied_at=db.now())
    add_vacancy(ext_id="2", source="other", url="https://bank.kz/job", status="applied", applied_at=db.now())
    add_vacancy(ext_id="3", status="applied", applied_at=(date.today() - timedelta(days=1)).isoformat() + "T10:00:00")
    assert db.count_today("vacancies", "applied_at", "applied", "AND source='hh'") == 1


def test_init_is_idempotent():
    db.init()
    db.init()
    assert db.q("SELECT COUNT(*) n FROM answers")[0]["n"] == len(db.DEFAULT_ANSWERS)


def test_job_runs_one_task_at_a_time():
    j, gate, started = Job(), threading.Event(), []
    fn = lambda: (started.append(1), gate.wait(2))
    results = []
    threads = [threading.Thread(target=lambda: results.append(j.start("t", fn))) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1
    gate.set()
    time.sleep(0.1)
    assert len(started) == 1 and not j.running


def test_job_error_is_logged_not_raised():
    j = Job()
    j.start("падающая задача", lambda: 1 / 0)
    time.sleep(0.2)
    assert "падающая задача" in db.q("SELECT msg FROM log ORDER BY id DESC LIMIT 1")[0]["msg"]


# ---------- guard rails ----------
def test_code_never_opens_the_one_click_response_url():
    """hh sends a response just by opening /applicant/vacancy_response?vacancyId=…: the bot must only ever click
    «Откликнуться» on the vacancy page, where the questionnaire and letter are handled."""
    from conftest import ROOT
    for f in ROOT.glob("*.py"):
        assert "vacancy_response?" not in f.read_text(), f.name
