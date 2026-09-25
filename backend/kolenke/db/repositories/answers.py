"""The answer base for HR robots and employer questionnaires, and the questions it could not answer."""
from kolenke.db.connection import execute, insert, now, query, transaction


def list_all() -> list[dict]:
    return query("SELECT * FROM answers ORDER BY id")


def save_many(items: list[dict]) -> None:
    """Items with an id are updated, new ones (id empty) are added when they have a topic or keywords."""
    with transaction() as c:
        for a in items:
            if a.get("id"):
                c.execute("UPDATE answers SET topic=?, keywords=?, answer=? WHERE id=?",
                          (a["topic"], a["keywords"], a["answer"], a["id"]))
            elif a.get("topic") or a.get("keywords"):
                c.execute("INSERT INTO answers(topic, keywords, answer) VALUES (?, ?, ?)",
                          (a["topic"], a["keywords"], a["answer"]))


def delete(aid: int) -> int:
    return execute("DELETE FROM answers WHERE id=?", (aid,))


def questions(limit: int = 200) -> list[dict]:
    return query("SELECT * FROM questions ORDER BY seen DESC, id DESC LIMIT ?", (limit,))


def remember_question(text: str, source: str) -> None:
    if execute("UPDATE questions SET seen = seen + 1 WHERE text=?", (text,)) == 0:
        insert("INSERT OR IGNORE INTO questions(text, source, created_at) VALUES (?, ?, ?)", (text, source, now()))


def delete_question(qid: int) -> int:
    return execute("DELETE FROM questions WHERE id=?", (qid,))
