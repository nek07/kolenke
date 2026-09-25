"""Database schema with numbered migrations tracked in PRAGMA user_version.

To change the schema, append a function to MIGRATIONS; never edit one that has already shipped.
Version 1 is the schema as it was before versioning: it is written to be safe on an empty file and on any
older kolenke database (missing tables and columns are added, nothing is dropped)."""
import sqlite3
from collections.abc import Callable

from kolenke.db.connection import transaction

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    ext_id TEXT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    company TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    note TEXT,
    created_at TEXT,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT NOT NULL UNIQUE,
    position TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    note TEXT,
    created_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT,
    keywords TEXT,
    answer TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT UNIQUE,
    source TEXT,
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
    status TEXT,
    created_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER,
    ts TEXT,
    kind TEXT,
    text TEXT
);
CREATE INDEX IF NOT EXISTS events_vacancy ON events(vacancy_id);

CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    msg TEXT
);
"""

VACANCY_COLUMNS = [
    ("resume", "TEXT"),          # resume title the response was sent with
    ("hh_state", "TEXT"),        # employer reaction from hh: не просмотрен, просмотрен, отказ, приглашение...
    ("hh_state_at", "TEXT"),
    ("letter_sent", "INTEGER"),  # 1 = cover letter really went out
    ("letter", "TEXT"),
    ("form_answers", "TEXT"),    # json [{q, a}] answers given in the employer questionnaire
    ("salary_text", "TEXT"),
    ("salary_from", "INTEGER"),
    ("salary_to", "INTEGER"),
    ("experience", "TEXT"),
    ("skill_match", "INTEGER"),  # hh «совпадение навыков», %
    ("match_info", "TEXT"),      # json [{ok, text}] why the vacancy passed (or failed) the filters
    ("invited_at", "TEXT"),
    ("reviewed_at", "TEXT"),
    ("stage", "TEXT"),           # pipeline stage after the response
    ("stage_manual", "INTEGER"), # 1 = moved by hand, hh sync won't pull it back
    ("stage_at", "TEXT"),
    ("notes", "TEXT"),
    ("next_step", "TEXT"),
    ("next_at", "TEXT"),
    ("remind_day", "INTEGER"),
    ("remind_hour", "INTEGER"),
    ("followup", "TEXT"),        # approved, sent, done, dismissed
    ("followup_text", "TEXT"),
    ("followup_at", "TEXT"),
    ("location", "TEXT"),
    ("country", "TEXT"),
    ("remote", "INTEGER"),
    ("summary", "TEXT"),
    ("contacts", "TEXT"),        # json {emails, phones, telegram, person}
    ("company_url", "TEXT"),
    ("skills", "TEXT"),
]

INVITE_STATES = ("приглашение", "собеседование", "выход на работу")


def _v1_base(c: sqlite3.Connection) -> None:
    c.executescript(BASE_SCHEMA)
    have = {r[1] for r in c.execute("PRAGMA table_info(vacancies)")}
    for col, typ in VACANCY_COLUMNS:
        if col not in have:
            c.execute(f"ALTER TABLE vacancies ADD COLUMN {col} {typ}")
    c.execute(
        f"UPDATE vacancies SET invited_at=COALESCE(hh_state_at, applied_at, created_at) "
        f"WHERE invited_at IS NULL AND hh_state IN ({','.join('?' * len(INVITE_STATES))})",
        INVITE_STATES,
    )


def _v2_indexes(c: sqlite3.Connection) -> None:
    c.execute("CREATE INDEX IF NOT EXISTS vacancies_source_status ON vacancies(source, status)")
    c.execute("CREATE INDEX IF NOT EXISTS vacancies_ext ON vacancies(source, ext_id)")
    c.execute("CREATE INDEX IF NOT EXISTS chat_items_status ON chat_items(status)")


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_v1_base, _v2_indexes]

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


def schema_version() -> int:
    with transaction() as c:
        return c.execute("PRAGMA user_version").fetchone()[0]


def migrate() -> int:
    """Brings the database to the latest version and seeds the answer base on a fresh install. Idempotent."""
    with transaction() as c:
        version = c.execute("PRAGMA user_version").fetchone()[0]
        for i, step in enumerate(MIGRATIONS[version:], start=version + 1):
            step(c)
            c.execute(f"PRAGMA user_version = {i}")
        if not c.execute("SELECT COUNT(*) FROM answers").fetchone()[0]:
            c.executemany("INSERT INTO answers(topic, keywords, answer) VALUES (?, ?, '')", DEFAULT_ANSWERS)
        return c.execute("PRAGMA user_version").fetchone()[0]
