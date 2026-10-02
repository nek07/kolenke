"""Runs a resume review in the background and assembles the report.

Reviews go through one worker thread in order: the market sample makes a few dozen requests to hh, and two at once
would only double the chance of a captcha. The page polls GET /api/resume-reviews/{id} for progress."""
import json
import queue
import threading
import traceback

from kolenke.db.repositories import reviews, settings
from kolenke.db.repositories.events import log
from kolenke.schemas.enums import GRADE_LABELS, CheckStatus, Grade
from kolenke.schemas.resume import Diff, Recommendation, ResumeReport, Rewrite
from kolenke.services.resume import ai, analyze, market
from kolenke.services.text import norm

_queue: queue.Queue[int] = queue.Queue()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def submit(rid: int) -> None:
    global _worker
    _queue.put(rid)
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, daemon=True, name="resume-review")
            _worker.start()


def _loop() -> None:
    while True:
        rid = _queue.get()
        try:
            run(rid)
        finally:
            _queue.task_done()


def run(rid: int, get=None) -> None:
    """The whole review; any failure ends up in the review's error, never in the worker."""
    row = reviews.get(rid)
    if not row:
        return
    try:
        report = build(rid, row, get)
        reviews.finish(rid, report.score, report.model_dump_json())
        log(f"Проверка резюме: {row['role']} ({GRADE_LABELS[Grade(row['grade'])]}) — {report.score} из 100")
    except Exception as e:
        traceback.print_exc()
        reviews.fail(rid, f"Не удалось проверить резюме: {e}")


def build(rid: int, row: dict, get=None) -> ResumeReport:
    s = settings.get()
    role, grade, text = row["role"], Grade(row["grade"]), row["resume_text"]
    progress = lambda msg: reviews.set_progress(rid, msg)  # noqa: E731

    progress("Читаю резюме")
    parsed = analyze.parse(text)

    sample = None
    if row["use_market"]:
        kwargs = {"get": get} if get else {}
        sample = market.collect(s.hh_domain, role, grade, s.hh_area, s.review_market_size, text, progress, **kwargs)

    progress("Прогоняю проверки")
    ctx = analyze.build_context(role, grade, sample)
    checks = analyze.run_checks(parsed, ctx)
    strengths, weaknesses = analyze.strengths_and_weaknesses(checks, parsed, sample)
    recs = analyze.recommendations(checks, ctx)
    rewrites = analyze.rewrite_templates(parsed)

    ai_part = None
    if row["use_ai"]:
        progress(f"Спрашиваю локальную модель {s.ai_model} (обычно 1–2 минуты)")
        result = ai.review(text, role, grade, checks, sample, s.ollama_url, s.ai_model)
        ai_part = result.part
        if not result.part.error:
            strengths = _merge(result.strengths, strengths, 7)
            weaknesses = _merge(result.weaknesses, weaknesses, 7)
            recs = sorted(recs + [Recommendation(priority=2, title="Совет ИИ", detail=t) for t in result.recommendations],
                          key=lambda r: r.priority)[:12]
            rewrites = _merge_rewrites(result.rewrites, rewrites)

    value = analyze.score(checks)
    report = ResumeReport(
        score=value, verdict=analyze.verdict(value, grade), role=role, role_profile=ctx.profile.label if ctx.profile else "",
        grade=grade, facts=analyze.facts(parsed), checks=checks, strengths=strengths, weaknesses=weaknesses,
        recommendations=recs, rewrites=rewrites, market=sample,
    )
    if ai_part:
        report.ai = ai_part
    report.diff = diff_with_previous(rid, report, text)
    return report


def _merge(first: list[str], second: list[str], limit: int) -> list[str]:
    out = []
    for item in first + second:
        if item and item not in out:
            out.append(item)
    return out[:limit]


def _merge_rewrites(by_ai: list[Rewrite], templates: list[Rewrite]) -> list[Rewrite]:
    covered = {norm(r.before) for r in by_ai}
    return (by_ai + [t for t in templates if norm(t.before) not in covered])[:8]


def diff_with_previous(rid: int, report: ResumeReport, text: str) -> Diff | None:
    prev = reviews.previous_done(rid, norm(report.role), report.grade.value)
    if not prev or not prev["report"]:
        return None
    old = ResumeReport.model_validate_json(prev["report"])
    before = {c.id: c for c in old.checks}
    fixed = [c.title for c in report.checks if c.status == CheckStatus.passed and c.id in before
             and before[c.id].status != CheckStatus.passed]
    worse = [c.title for c in report.checks if c.id in before and _rank(c.status) < _rank(before[c.id].status)]
    added = [x for x in report.facts.skills_found if x not in set(old.facts.skills_found)]
    return Diff(previous_id=prev["id"], previous_score=old.score, score_delta=report.score - old.score,
                fixed=fixed, new_issues=worse, skills_added=added[:10], same_resume=prev["resume_text"] == text)


def _rank(status: CheckStatus) -> int:
    return {CheckStatus.fail: 0, CheckStatus.warn: 1, CheckStatus.passed: 2}[status]


# ---------- sharing ----------
MARK = {CheckStatus.passed: "✅", CheckStatus.warn: "⚠️", CheckStatus.fail: "❌"}


def markdown(row: dict, report: ResumeReport) -> str:
    """The report as a Markdown file: to send to a mentor or a friend, or to keep next to the resume."""
    g = GRADE_LABELS[report.grade]
    out = [f"# Проверка резюме: {report.role}, {g}", "",
           f"**{report.score} из 100.** {report.verdict}", "",
           f"Дата: {row['created_at'][:10]} · файл: {row['source_name']}"]
    if report.diff:
        d = report.diff
        sign = "+" if d.score_delta >= 0 else ""
        out += ["", f"По сравнению с прошлой проверкой: {sign}{d.score_delta} (было {d.previous_score})"
                + (", резюме то же — изменился рынок." if d.same_resume else ".")]
        if d.fixed:
            out.append("Исправлено: " + ", ".join(d.fixed) + ".")
    if report.ai.used and report.ai.summary:
        out += ["", "## Мнение ИИ", "", report.ai.summary]
        if report.ai.grade_comment:
            out += ["", f"Грейд: {report.ai.grade_fit}. {report.ai.grade_comment}"]
    if report.strengths:
        out += ["", "## Сильные стороны", ""] + [f"- {x}" for x in report.strengths]
    if report.weaknesses:
        out += ["", "## Что мешает", ""] + [f"- {x}" for x in report.weaknesses]
    if report.recommendations:
        out += ["", "## Что сделать", ""] + [f"{i}. **{r.title}.** {r.detail}" for i, r in enumerate(report.recommendations, 1)]
    if report.rewrites:
        out += ["", "## Как усилить формулировки", ""]
        for r in report.rewrites:
            out += [f"- Было: {r.before}", f"  Стало: {r.after}", f"  _{r.why}_", ""]
    out += ["", "## Проверки", ""]
    for group in dict.fromkeys(c.group for c in report.checks):
        out += [f"### {group}", ""] + [f"- {MARK[c.status]} **{c.title}.** {c.detail}" + (f" → {c.fix}" if c.fix else "")
                                       for c in report.checks if c.group == group] + [""]
    m = report.market
    if m and m.skills:
        out += ["## Рынок", "", f"Вакансий в выборке: {m.sample_size} ({', '.join(m.sources)}). "
                f"Покрытие частых требований: {m.coverage}%.", ""]
        out += [f"- {'✅' if s.have else '➖'} {s.name} — {s.share}%" for s in m.skills[:15]]
        if m.salary:
            out += ["", f"Зарплаты ({m.salary.currency}): медиана {m.salary.median:,}, "
                    f"середина рынка {m.salary.low:,}–{m.salary.high:,} ({m.salary.count} вакансий с зарплатой)".replace(",", " ")]
    out += ["", "_Сделано в kolenke_"]
    return "\n".join(out) + "\n"


def recover() -> None:
    """Called at startup: reviews that were running when the server stopped will not finish on their own."""
    reviews.fail_unfinished("Проверка прервалась из-за перезапуска, запустите её ещё раз")


def load_report(row: dict) -> ResumeReport | None:
    return ResumeReport.model_validate(json.loads(row["report"])) if row.get("report") else None
