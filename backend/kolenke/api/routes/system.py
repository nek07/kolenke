"""Tasks, the dashboard status, statistics, search and CSV exports."""
import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from kolenke.db.repositories import stats
from kolenke.db.repositories.events import log
from kolenke.schemas.api import Ok, SearchResult, Stats, Status, TaskInfo
from kolenke.services import dashboard
from kolenke.workers.runner import runner
from kolenke.workers.tasks import TASKS

router = APIRouter(tags=["system"])


@router.get("/jobs", response_model=list[TaskInfo])
def list_tasks():
    return [TaskInfo(key=t.key, title=t.title) for t in TASKS.values()]


@router.post("/jobs/stop", response_model=Ok)
def stop_task():
    runner.stop()
    return Ok()


@router.post("/jobs/{key}", response_model=Ok)
def start_task(key: str):
    task = TASKS.get(key)
    if not task:
        raise HTTPException(404, "Нет такой задачи")
    if not runner.start(task.title, task.run):
        raise HTTPException(409, f"Уже выполняется: {runner.name}")
    log(f"▶ {task.title}")
    return Ok()


@router.get("/status", response_model=Status)
def get_status():
    return dashboard.status()


@router.get("/stats", response_model=Stats)
def get_stats():
    return dashboard.statistics()


@router.get("/search", response_model=SearchResult)
def global_search(q: str = ""):
    return dashboard.search(q)


@router.get("/export/{what}", response_class=Response,
            responses={200: {"content": {"text/csv": {}}, "description": "CSV for Excel (semicolons, UTF-8 BOM)"}})
def export_csv(what: str):
    if what not in stats.EXPORTS:
        raise HTTPException(404, "Нет такой выгрузки")
    filename, rows = stats.export(what)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")  # ; so Excel with Russian locale splits columns
    w.writerow(rows[0].keys() if rows else ["нет данных"])
    w.writerows([list(r.values()) for r in rows])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})
