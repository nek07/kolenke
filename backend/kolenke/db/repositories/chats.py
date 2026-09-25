"""Messages from hh chats that the bot answered or passed to you."""
from kolenke.db.connection import execute, insert, now, one, query, scalar
from kolenke.schemas.enums import ChatStatus

HISTORY = (ChatStatus.sent, ChatStatus.auto_sent, ChatStatus.approved, ChatStatus.closed)


def get(cid: int) -> dict | None:
    return one("SELECT * FROM chat_items WHERE id=?", (cid,))


def by_status(status: str, limit: int = 300) -> list[dict]:
    return query("SELECT * FROM chat_items WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))


def history(limit: int = 300) -> list[dict]:
    return query(f"SELECT * FROM chat_items WHERE status IN ({','.join('?' * len(HISTORY))}) ORDER BY id DESC LIMIT ?",
                 (*HISTORY, limit))


def visible() -> list[dict]:
    return query("SELECT * FROM chat_items WHERE status != 'hidden' ORDER BY id")


def visible_newest_first() -> list[dict]:
    return query("SELECT id, chat_id, company, vacancy, message, status, created_at FROM chat_items "
                 "WHERE status != 'hidden' ORDER BY id DESC")


def is_known(msg_id: str) -> bool:
    return bool(one("SELECT 1 FROM chat_items WHERE msg_id=?", (msg_id,)))


def add(chat_id: str, msg_id: str, company: str, vacancy: str, message: str, robot: bool, reply: str | None,
        status: ChatStatus) -> int | None:
    sent_at = now() if status == ChatStatus.auto_sent else None
    return insert(
        "INSERT OR IGNORE INTO chat_items(chat_id, msg_id, company, vacancy, message, robot, reply, status, "
        "created_at, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (chat_id, msg_id, company, vacancy, message, int(robot), reply, status, now(), sent_at),
    )


def approve(cid: int, reply: str) -> int:
    return execute("UPDATE chat_items SET status='approved', reply=? WHERE id=?", (reply, cid))


def set_status(cid: int, status: ChatStatus) -> int:
    if status == ChatStatus.sent:
        return execute("UPDATE chat_items SET status=?, sent_at=? WHERE id=?", (status, now(), cid))
    return execute("UPDATE chat_items SET status=? WHERE id=?", (status, cid))


def approved() -> list[dict]:
    return query("SELECT * FROM chat_items WHERE status='approved' ORDER BY id")


def count(status: str) -> int:
    return scalar("SELECT COUNT(*) FROM chat_items WHERE status=?", (status,))
