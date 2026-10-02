"""Resume review: send a resume (file, text, or the one from the settings), get a report for a role and grade."""
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from kolenke.db.repositories import reviews, settings
from kolenke.schemas.api import Ok
from kolenke.schemas.enums import GRADE_LABELS, Grade
from kolenke.schemas.resume import AiStatus, ReviewDetail, ReviewOptions, ReviewSummary, RoleOption
from kolenke.services.resume import ai, review
from kolenke.services.resume.extract import ExtractError, clean, extract_text
from kolenke.services.resume.profiles import ROLES

router = APIRouter(prefix="/resume-reviews", tags=["resume"])


def _summary(row: dict) -> dict:
    return {**row, "use_market": bool(row["use_market"]), "use_ai": bool(row["use_ai"]), "source_name": row["source_name"] or ""}


@router.get("/options", response_model=ReviewOptions)
def review_options():
    return ReviewOptions(
        roles=[RoleOption(key=r.key, label=r.label) for r in ROLES],
        grades=[RoleOption(key=g.value, label=GRADE_LABELS[g]) for g in Grade],
        ai_available=settings.get().ai_review,
    )


@router.get("/ai-status", response_model=AiStatus)
def ai_status():
    """Whether Ollama runs on this computer and the chosen model is downloaded."""
    s = settings.get()
    return ai.status(s.ollama_url, s.ai_model)


@router.post("", response_model=ReviewSummary, status_code=201)
async def create_review(
    role: Annotated[str, Form(min_length=2, max_length=120)],
    grade: Annotated[Grade, Form()],
    use_market: Annotated[bool, Form()] = True,
    use_ai: Annotated[bool, Form()] = False,
    use_saved_file: Annotated[bool, Form()] = False,
    text: Annotated[str | None, Form(max_length=60000)] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    """One of: a file (PDF, DOCX, TXT), pasted text, or use_saved_file for the resume uploaded in the settings."""
    s = settings.get()
    if use_ai and not s.ai_review:
        raise HTTPException(400, "ИИ-разбор выключен: включите его в настройках")
    try:
        if file is not None and file.filename:
            source = Path(file.filename).name
            resume_text = extract_text(source, await file.read())
        elif text and text.strip():
            source, resume_text = "Текст из формы", clean(text)
            if len(resume_text) < 80:
                raise ExtractError("Слишком короткий текст: вставьте резюме целиком")
        elif use_saved_file:
            path = Path(s.resume_file) if s.resume_file else None
            if not path or not path.is_file():
                raise ExtractError("В настройках нет файла резюме")
            source, resume_text = path.name, extract_text(path.name, path.read_bytes())
        else:
            raise ExtractError("Приложите файл резюме или вставьте текст")
    except ExtractError as e:
        raise HTTPException(400, str(e)) from e
    rid = reviews.create(role.strip(), grade.value, source, resume_text, use_market, use_ai)
    review.submit(rid)
    return _summary(reviews.get(rid))


@router.get("", response_model=list[ReviewSummary])
def list_reviews():
    return [_summary(r) for r in reviews.history()]


@router.get("/{rid}", response_model=ReviewDetail)
def get_review(rid: int):
    row = reviews.get(rid)
    if not row:
        raise HTTPException(404, "Нет такой проверки")
    return {**_summary(row), "report": review.load_report(row)}


@router.get("/{rid}/export", response_class=Response,
            responses={200: {"content": {"text/markdown": {}}, "description": "The report as a Markdown file"}})
def export_review(rid: int):
    row = reviews.get(rid)
    report = review.load_report(row) if row else None
    if not report:
        raise HTTPException(404, "Отчёт ещё не готов")
    filename = f"resume-review-{rid}.md"
    return Response(review.markdown(row, report), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.post("/{rid}/rerun", response_model=ReviewSummary, status_code=201)
def rerun_review(rid: int):
    """The same resume, role and grade again: after the market moved, or to see the effect of new settings."""
    row = reviews.get(rid)
    if not row:
        raise HTTPException(404, "Нет такой проверки")
    use_ai = bool(row["use_ai"]) and settings.get().ai_review
    new_id = reviews.create(row["role"], row["grade"], row["source_name"], row["resume_text"], bool(row["use_market"]), use_ai)
    review.submit(new_id)
    return _summary(reviews.get(new_id))


@router.delete("/{rid}", response_model=Ok)
def delete_review(rid: int):
    if not reviews.delete(rid):
        raise HTTPException(404, "Нет такой проверки")
    return Ok()
