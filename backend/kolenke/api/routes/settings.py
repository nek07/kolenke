from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from kolenke.config import get_config
from kolenke.db.repositories import settings
from kolenke.schemas.api import ResumeUploaded
from kolenke.schemas.settings import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

RESUME_TYPES = (".pdf", ".doc", ".docx")


def _out() -> SettingsOut:
    s = settings.get()
    return SettingsOut(**s.model_dump(), has_password=bool(s.smtp_password),
                       resume_name=Path(s.resume_file).name if s.resume_file else "")


@router.get("", response_model=SettingsOut)
def get_settings():
    return _out()


@router.patch("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate):
    changes = body.model_dump(exclude_unset=True)
    if not changes.get("smtp_password"):
        changes.pop("smtp_password", None)  # empty keeps the stored password
    changes = {k: v for k, v in changes.items() if v is not None}
    settings.save(changes)
    return _out()


@router.post("/resume", response_model=ResumeUploaded)
async def upload_resume(file: UploadFile = File(...)):
    name = Path(file.filename or "").name
    if not name.lower().endswith(RESUME_TYPES):
        raise HTTPException(400, "Нужен PDF, DOC или DOCX")
    path = get_config().resume_dir / name
    path.write_bytes(await file.read())
    settings.save({"resume_file": str(path)})
    return ResumeUploaded(name=name)
