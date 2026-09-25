"""Answer base: pick a prepared answer for a question from an HR robot or a response questionnaire."""
import re

from kolenke.db.repositories import answers


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е"))


def match(question: str) -> tuple[str | None, str]:
    """(topic, answer) of the best matching entry; answer is '' when the entry is not filled in."""
    q = _norm(question)
    best, best_score = None, 0
    for a in answers.list_all():
        kws = [_norm(k).strip() for k in (a["keywords"] or "").split(",") if k.strip()]
        hits = [k for k in kws if k in q]
        score = len(hits) * 100 - len(kws)  # on a tie the narrower topic (fewer keywords) wins
        if score > best_score:
            best, best_score = a, score
    if not best:
        return None, ""
    return best["topic"], (best["answer"] or "").strip()


def remember_unknown(question: str, source: str) -> None:
    """A question the base could not answer: shown in «Вопросы без ответа», repeats are counted."""
    text = (question or "").strip()[:1000]
    if text:
        answers.remember_question(text, source)
