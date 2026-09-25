from fastapi import APIRouter

from kolenke.db.repositories import vacancies
from kolenke.schemas.api import Pipeline, Reminders
from kolenke.schemas.enums import STAGE_LABELS, Stage
from kolenke.services import pipeline

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline", response_model=Pipeline)
def get_pipeline():
    pipeline.ensure_stages()
    return Pipeline(stages=[{"id": s, "label": STAGE_LABELS[s]} for s in Stage], cards=vacancies.pipeline_cards())


@router.get("/reminders", response_model=Reminders)
def get_reminders():
    return pipeline.reminders()
