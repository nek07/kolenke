"""Answer base: pick a prepared answer for a question from an HR robot or a response questionnaire."""
import re

import db


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е"))


def match(question: str):
    """Return (topic, answer) of the best matching entry; answer is '' when the entry is not filled in."""
    q = _norm(question)
    best, best_score = None, 0
    for a in db.q("SELECT * FROM answers"):
        kws = [_norm(k).strip() for k in (a["keywords"] or "").split(",") if k.strip()]
        hits = [k for k in kws if k in q]
        score = len(hits) * 100 - len(kws)  # on a tie the narrower topic (fewer keywords) wins
        if score > best_score:
            best, best_score = a, score
    if not best:
        return None, ""
    return best["topic"], (best["answer"] or "").strip()


def remember_unknown(question: str, source: str):
    text = (question or "").strip()[:1000]
    if not text:
        return
    if db.x("UPDATE questions SET seen = seen + 1 WHERE text=?", (text,)) == 0:
        db.x("INSERT OR IGNORE INTO questions(text, source, created_at) VALUES (?, ?, ?)", (text, source, db.now()))
