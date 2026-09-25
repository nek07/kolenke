from fastapi import APIRouter, HTTPException

from kolenke.db.repositories import settings, vacancies
from kolenke.schemas.api import (
    Count,
    Draft,
    FollowupClose,
    FollowupSend,
    Ids,
    Ok,
    PipelineUpdate,
    QueueNew,
    Started,
    StatusChange,
    ToCompaniesResult,
    Vacancy,
    VacancyAdd,
    VacancyDetail,
)
from kolenke.schemas.enums import Followup, VacancySource, VacancyStatus
from kolenke.services import companies as companies_service
from kolenke.services import pipeline
from kolenke.services import vacancies as service
from kolenke.services.text import fill
from kolenke.workers.runner import runner
from kolenke.workers.tasks import TASKS

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


def _get_or_404(vid: int) -> dict:
    v = vacancies.get(vid)
    if not v:
        raise HTTPException(404, "Вакансия не найдена")
    return v


@router.get("", response_model=list[Vacancy])
def list_vacancies(source: VacancySource | None = None, status: VacancyStatus | None = None):
    return vacancies.find(source, status)


@router.post("", response_model=Ok)
def add_vacancy(body: VacancyAdd):
    vacancies.add_manual(body.source, body.url.strip(), body.title or body.url, body.company)
    return Ok()


@router.get("/review", response_model=list[Vacancy])
def review_queue():
    """New hh vacancies waiting for «Откликнуться» / «Пропустить»."""
    return vacancies.review_queue(settings.get().f_sort_match)


@router.patch("/status", response_model=Ok)
def change_vacancy_status(body: StatusChange):
    service.set_status(body.ids, body.status, body.review)
    return Ok()


@router.post("/queue-new", response_model=Count)
def queue_all_new(body: QueueNew):
    return Count(count=service.queue_all_new(body.source))


@router.post("/delete", response_model=Ok)
def delete_vacancies(body: Ids):
    vacancies.delete(body.ids)
    return Ok()


@router.post("/to-companies", response_model=ToCompaniesResult)
def to_companies(body: Ids):
    """E-mails from vacancies on other sites go to «Письма компаниям»."""
    return companies_service.from_vacancies(body.ids)


@router.get("/{vid}", response_model=VacancyDetail)
def vacancy_detail(vid: int):
    d = service.detail(vid)
    if not d:
        raise HTTPException(404, "Вакансия не найдена")
    return d


@router.patch("/{vid}/pipeline", response_model=VacancyDetail)
def update_pipeline(vid: int, body: PipelineUpdate):
    try:
        pipeline.update(vid, body.model_dump(exclude_unset=True))
    except pipeline.NotFound:
        raise HTTPException(404, "Вакансия не найдена") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return service.detail(vid)


@router.get("/{vid}/followup-draft", response_model=Draft)
def followup_draft(vid: int):
    v = _get_or_404(vid)
    s = settings.get()
    return Draft(text=fill(s.followup_template, s, v["company"], v["title"]))


@router.post("/{vid}/followup", response_model=Started)
def send_followup(vid: int, body: FollowupSend):
    _get_or_404(vid)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    vacancies.set_followup(vid, Followup.approved, text)
    task = TASKS["hh_followups"]
    return Started(started=runner.start(task.title, task.run))


@router.post("/{vid}/followup/close", response_model=Ok)
def close_followup(vid: int, body: FollowupClose):
    _get_or_404(vid)
    vacancies.set_followup(vid, Followup(body.action))
    return Ok()
