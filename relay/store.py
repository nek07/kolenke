"""Cloud panel storage: accounts, invites, sessions, pairing codes, agents. No vacancies, resumes or hh data here —
those stay on each user's own computer with the agent."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(os.environ.get("RELAY_DATA") or Path(__file__).parent / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "relay.db"
SESSION_DAYS = 30
PAIR_MINUTES = 10

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,          -- scrypt$salt$hash
    is_admin INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS invites (
    code TEXT PRIMARY KEY,
    created_at TEXT,
    used_by INTEGER,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS pair_codes (
    code TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TEXT,
    last_seen TEXT
);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def q(sql, args=()):
    with _lock:
        c = _conn()
        try:
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()


def x(sql, args=()):
    with _lock:
        c = _conn()
        try:
            with c:
                return c.execute(sql, args).rowcount
        finally:
            c.close()


def init():
    with _lock:
        c = _conn()
        with c:
            c.executescript(SCHEMA)
        c.close()
    DATA_DIR.chmod(0o700)


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- passwords ----------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return f"scrypt${salt}${h}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
    except ValueError:
        return False
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return hmac.compare_digest(got, h)


# ---------- invites & users ----------
def new_invite() -> str:
    code = "-".join(secrets.token_hex(2).upper() for _ in range(3))  # e.g. 7F3A-91C2-0B4E
    x("INSERT INTO invites(code, created_at) VALUES (?, ?)", (code, now()))
    return code


def register(email: str, password: str, invite: str):
    """Returns the new user id, or raises ValueError with a message for the person."""
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 200:
        raise ValueError("Укажите настоящий email")
    if len(password or "") < 8:
        raise ValueError("Пароль — не короче 8 символов")
    first = not q("SELECT 1 FROM users LIMIT 1")  # the first account becomes the owner
    inv = (invite or "").strip().upper()
    # always by invite: on a public server a stranger must not become the owner by registering first.
    # The owner makes the first code on the server itself: python -m relay.manage invite
    if q("SELECT 1 FROM users WHERE email=?", (email,)):
        raise ValueError("Такой email уже зарегистрирован")
    # claim the invite atomically, so one code can't create two accounts at the same moment
    if not x("UPDATE invites SET used_by=0, used_at=? WHERE code=? AND used_by IS NULL", (now(), inv)):
        raise ValueError("Приглашение не найдено или уже использовано")
    try:
        x("INSERT INTO users(email, password, is_admin, created_at) VALUES (?, ?, ?, ?)",
          (email, hash_password(password), int(first), now()))
    except Exception:
        x("UPDATE invites SET used_by=NULL, used_at=NULL WHERE code=?", (inv,))  # give the code back
        raise ValueError("Такой email уже зарегистрирован")
    uid = q("SELECT id FROM users WHERE email=?", (email,))[0]["id"]
    x("UPDATE invites SET used_by=? WHERE code=?", (uid, inv))
    return uid


def authenticate(email: str, password: str):
    rows = q("SELECT * FROM users WHERE email=?", ((email or "").strip().lower(),))
    if rows and check_password(password or "", rows[0]["password"]):
        return rows[0]
    # same work on a wrong email, so timing doesn't reveal which emails exist
    check_password(password or "", "scrypt$" + "00" * 16 + "$00")
    return None


# ---------- sessions ----------
def new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    x("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
      (sha(token), user_id, (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")))
    return token


def session_user(token: str):
    if not token:
        return None
    rows = q("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at > ?",
             (sha(token), now()))
    return rows[0] if rows else None


def end_session(token: str):
    x("DELETE FROM sessions WHERE token_hash=?", (sha(token or ""),))


# ---------- pairing & agents ----------
def new_pair_code(user_id: int) -> str:
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))  # no 0/O, 1/I
    x("DELETE FROM pair_codes WHERE user_id=? OR expires_at < ?", (user_id, now()))
    x("INSERT INTO pair_codes(code, user_id, expires_at) VALUES (?, ?, ?)",
      (code, user_id, (datetime.now() + timedelta(minutes=PAIR_MINUTES)).isoformat(timespec="seconds")))
    return code


def pair(code: str, name: str):
    """Exchanges a one-time pairing code for a long-lived agent token. Returns (token, user) or raises ValueError."""
    rows = q("SELECT * FROM pair_codes WHERE code=? AND expires_at > ?", ((code or "").strip().upper(), now()))
    if not rows:
        raise ValueError("Код не найден или истёк. Получите новый в панели")
    uid = rows[0]["user_id"]
    x("DELETE FROM pair_codes WHERE code=?", (rows[0]["code"],))
    token = secrets.token_urlsafe(40)
    x("INSERT INTO agents(user_id, token_hash, name, created_at) VALUES (?, ?, ?, ?)",
      (uid, sha(token), (name or "компьютер")[:80], now()))
    return token, q("SELECT id, email FROM users WHERE id=?", (uid,))[0]


def agent_by_token(token: str):
    rows = q("SELECT a.*, u.email FROM agents a JOIN users u ON u.id=a.user_id WHERE a.token_hash=?", (sha(token or ""),))
    return rows[0] if rows else None


def touch_agent(agent_id: int):
    x("UPDATE agents SET last_seen=? WHERE id=?", (now(), agent_id))


def agents_of(user_id: int):
    return q("SELECT id, name, created_at, last_seen FROM agents WHERE user_id=? ORDER BY id DESC", (user_id,))


def remove_agent(user_id: int, agent_id: int) -> bool:
    return x("DELETE FROM agents WHERE id=? AND user_id=?", (agent_id, user_id)) > 0
