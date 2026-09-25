import os
import sqlite3
import threading
from datetime import datetime, date, timedelta
from pathlib import Path

DATA_DIR = Path(os.environ.get("JOBBOT_DATA") or Path(__file__).parent / "data")
DATA_DIR.mkdir(exist_ok=True)
DATA_DIR.chmod(0o700)  # Gmail app password and the hh session live here: not for other users of this Mac
DB_PATH = DATA_DIR / "jobbot.db"

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,             -- hh, habr, superjob, linkedin, other
    ext_id TEXT,                      -- id on the source site
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    company TEXT,
    status TEXT NOT NULL DEFAULT 'new', -- new, queued, applied, skipped, error
    note TEXT,
    created_at TEXT,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT NOT NULL UNIQUE,
    position TEXT,
    status TEXT NOT NULL DEFAULT 'new', -- new, queued, sent, error
    note TEXT,
    created_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT,
    keywords TEXT,      -- comma-separated parts of words to look for in a question
    answer TEXT
);

CREATE TABLE IF NOT EXISTS questions (   -- questions the bot could not answer, to add to the answer base
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT UNIQUE,
    source TEXT,        -- chat / form
    seen INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS chat_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    msg_id TEXT UNIQUE,
    company TEXT,
    vacancy TEXT,
    message TEXT,
    reply TEXT,
    robot INTEGER,
    status TEXT,        -- pending, approved, sent, auto_sent, hidden
    created_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS events (    -- history of one vacancy for the side panel
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER,
    ts TEXT,
    kind TEXT,          -- found, filtered, queued, skipped, applied, letter, form, error, employer
    text TEXT
);
CREATE INDEX IF NOT EXISTS events_vacancy ON events(vacancy_id);

CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    msg TEXT
);
"""

DEFAULTS = {
    "full_name": "",
    "phone": "",
    "desired_position": "",
    "hh_domain": "hh.kz",
    "hh_mode": "resume",      # resume = vacancies hh recommends for a resume, query = text search
    "hh_resume_hash": "",
    "hh_resumes": "[]",       # cached list of the user's hh resumes (json)
    "hh_query": "",
    "hh_area": "",            # e.g. 160 = Алматы, 159 = Астана; empty = all
    "hh_pages": "3",
    "hh_daily_limit": "50",   # safety limit against captcha, not a goal
    "hh_weekly_goal": "150",  # responses per week
    "hh_pause_min": "4",      # seconds between two hh responses (random in [min, max])
    "hh_pause_max": "9",
    "chat_max": "20",         # unread chats handled per check
    "chat_robot_steps": "10", # HR-robot questions answered in a row in one chat
    "other_max_details": "40",  # new vacancy pages opened per check on Хабр Карьера / Enbek
    "hh_exclude": "",         # comma-separated words; vacancy title containing any is skipped
    "f_salary_min": "",       # skip vacancies whose salary (upper bound) is below this
    "f_skip_no_salary": "0",
    "f_experience": "",       # hh experience codes, comma-separated: noExperience, between1And3, between3And6, moreThan6
    "f_exclude_companies": "",  # one per line or comma-separated, part of the name is enough
    "f_skip_rejected": "1",   # don't apply again to a company that already rejected
    "f_min_match": "0",       # minimal hh skill match, %; vacancies without the mark are kept
    "f_sort_match": "1",      # best skill match first in the review and the apply queue
    "hh_letter_template": (
        "Здравствуйте!\n\nМеня заинтересовала вакансия «{position}» в компании {company}. "
        "Буду рад(а) обсудить, чем могу быть полезен(на) вашей команде.\n\n"
        "С уважением,\n{name}\n{phone}"
    ),
    "smtp_host": "smtp.gmail.com",
    "smtp_port": "465",
    "smtp_user": "",
    "smtp_password": "",
    "mail_daily_limit": "80",
    "mail_delay_min": "40",
    "mail_delay_max": "90",
    "mail_subject_template": "Резюме: {name} — {position}",
    "mail_body_template": (
        "Здравствуйте!\n\nМеня зовут {name}. Хотел(а) бы предложить свою кандидатуру "
        "на позицию «{position}» в {company}. Резюме во вложении.\n\n"
        "Буду благодарен(на) за обратную связь.\n\nС уважением,\n{name}\n{phone}"
    ),
    "resume_file": "",
    "autopilot_on": "0",
    "autopilot_mode": "review",  # review = find and notify, you swipe; auto = apply at once
    "autopilot_interval": "30",
    "autopilot_from": "8",
    "autopilot_to": "22",
    "chat_auto": "1",         # answer HR robots automatically when the answer base has an answer
    "other_query": "",        # search text for Хабр Карьера / Enbek; empty = desired position
    "other_sites": "habr,enbek",
    "other_pages": "2",
    "other_countries": "",    # e.g. «Казахстан, удалённо»; empty = any country
    "other_monitor": "1",     # check other sites in every autopilot cycle
    "followup_days": "5",     # suggest reminding about yourself after this many days without a reaction
    "followup_template": (
        "Здравствуйте! Несколько дней назад я откликнулся(ась) на вакансию «{position}». "
        "Подскажите, пожалуйста, актуальна ли она и удобно ли обсудить мою кандидатуру? "
        "Буду рад(а) ответить на любые вопросы.\n\nС уважением,\n{name}"
    ),
}

DEFAULT_ANSWERS = [
    ("Зарплатные ожидания", "зарплат, ожидани, доход, оклад, вилк, сколько хотите"),
    ("Опыт работы", "опыт, стаж, сколько лет"),
    ("Официальное трудоустройство", "официальн, подтвердить"),
    ("Английский", "английск, english"),
    ("Формат работы", "формат, удалён, удален, офис, гибрид"),
    ("Когда можете выйти", "приступить, выйти на работу, когда сможете, когда готовы"),
    ("Город / переезд", "город, переезд, релокац, проживаете, где находитесь"),
    ("Контакты", "telegram, телеграм, whatsapp, ватсап, номер телефона, связаться"),
    ("GitHub / портфолио", "github, гитхаб, портфолио, примеры работ"),
    ("Стек технологий", "стек, технологи, фреймворк"),
    ("SQL", "sql"),
    ("Образование", "образовани, вуз, университет"),
    ("Тестовое задание", "тестов"),
    ("Гражданство", "гражданств"),
]


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


MIGRATIONS = [
    ("vacancies", "resume", "TEXT"),        # resume title the response was sent with
    ("vacancies", "hh_state", "TEXT"),      # employer reaction from hh: не просмотрен, просмотрен, отказ, приглашение...
    ("vacancies", "hh_state_at", "TEXT"),
    ("vacancies", "letter_sent", "INTEGER"),  # 1 = cover letter really went out
    ("vacancies", "letter", "TEXT"),        # the cover letter text that was sent
    ("vacancies", "form_answers", "TEXT"),  # json [{q, a}] answers given in the employer questionnaire
    ("vacancies", "salary_text", "TEXT"),
    ("vacancies", "salary_from", "INTEGER"),
    ("vacancies", "salary_to", "INTEGER"),
    ("vacancies", "experience", "TEXT"),
    ("vacancies", "skill_match", "INTEGER"),  # hh «совпадение навыков», %
    ("vacancies", "match_info", "TEXT"),    # json [{ok, text}] why the vacancy passed (or failed) the filters
    ("vacancies", "invited_at", "TEXT"),    # first time an invitation was seen
    ("vacancies", "reviewed_at", "TEXT"),   # when you swiped it in the review
    # after the response: pipeline card
    ("vacancies", "stage", "TEXT"),         # applied, viewed, invited, interview, offer, declined (see pipeline.py)
    ("vacancies", "stage_manual", "INTEGER"),  # 1 = you moved it yourself, hh sync won't pull it back
    ("vacancies", "stage_at", "TEXT"),
    ("vacancies", "notes", "TEXT"),
    ("vacancies", "next_step", "TEXT"),     # e.g. «Собеседование»
    ("vacancies", "next_at", "TEXT"),       # local datetime of the next step
    ("vacancies", "remind_day", "INTEGER"), # 1 = «завтра …» notification shown
    ("vacancies", "remind_hour", "INTEGER"),
    ("vacancies", "followup", "TEXT"),      # approved, sent, done, dismissed
    ("vacancies", "followup_text", "TEXT"),
    ("vacancies", "followup_at", "TEXT"),
    # other sites (Хабр Карьера, Enbek)
    ("vacancies", "location", "TEXT"),
    ("vacancies", "country", "TEXT"),
    ("vacancies", "remote", "INTEGER"),
    ("vacancies", "summary", "TEXT"),       # short description
    ("vacancies", "contacts", "TEXT"),      # json {emails, phones, telegram, person}
    ("vacancies", "company_url", "TEXT"),
    ("vacancies", "skills", "TEXT"),
]

INVITE_STATES = ("приглашение", "собеседование", "выход на работу")


def init():
    with _lock:
        c = connect()
        with c:
            c.executescript(SCHEMA)
            for table, col, typ in MIGRATIONS:
                if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            c.execute(
                f"UPDATE vacancies SET invited_at=COALESCE(hh_state_at, applied_at, created_at) "
                f"WHERE invited_at IS NULL AND hh_state IN ({','.join('?' * len(INVITE_STATES))})", INVITE_STATES
            )
            for k, v in DEFAULTS.items():
                c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
            if not c.execute("SELECT COUNT(*) FROM answers").fetchone()[0]:
                c.executemany("INSERT INTO answers(topic, keywords, answer) VALUES (?, ?, '')", DEFAULT_ANSWERS)
        c.close()


def now():
    return datetime.now().isoformat(timespec="seconds")


def q(sql, args=()):
    with _lock:
        c = connect()
        try:
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()


def x(sql, args=()):
    with _lock:
        c = connect()
        try:
            with c:  # commits, or rolls back on error
                return c.execute(sql, args).rowcount
        finally:
            c.close()


def event(vacancy_id, kind: str, text: str):
    x("INSERT INTO events(vacancy_id, ts, kind, text) VALUES (?, ?, ?, ?)", (vacancy_id, now(), kind, text))


def week_start() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def get_settings():
    return {r["key"]: r["value"] for r in q("SELECT key, value FROM settings")}


def set_settings(values: dict):
    with _lock, connect() as c:
        for k, v in values.items():
            if k in DEFAULTS:
                c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, str(v)))


def log(msg: str):
    print(msg, flush=True)
    x("INSERT INTO log(ts, msg) VALUES (?, ?)", (now(), msg))


def count_today(table: str, col: str, status: str, where: str = "") -> int:
    today = date.today().isoformat()
    return q(f"SELECT COUNT(*) n FROM {table} WHERE status=? AND {col} LIKE ? {where}", (status, today + "%"))[0]["n"]


def num(s: dict, key: str, lo: int = 1, hi: int | None = None) -> int:
    """A user-set limit as an int: garbage or empty falls back to the default, then kept within [lo, hi]."""
    try:
        v = int(float(str(s.get(key, "")).replace(",", ".").strip()))
    except ValueError:
        v = int(DEFAULTS[key])
    v = max(lo, v)
    return min(v, hi) if hi is not None else v


def fill(template: str, **kw) -> str:
    s = get_settings()
    values = {"name": s["full_name"], "phone": s["phone"], "company": "", "position": ""}
    values.update({k: (v or "") for k, v in kw.items()})
    if not values["position"]:
        values["position"] = s["desired_position"]
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out
