from fastapi import APIRouter, File, HTTPException, UploadFile

from kolenke.db.repositories import companies, settings
from kolenke.schemas.api import (
    Added,
    Company,
    CompanyAdd,
    CompanyStatusChange,
    CompanyUpdate,
    Ids,
    MailPreview,
    MailTest,
    Ok,
)
from kolenke.schemas.enums import CompanyStatus
from kolenke.services import companies as service
from kolenke.services import mailer

router = APIRouter(tags=["companies"])

MAX_IMPORT_BYTES = 5 * 1024 * 1024


@router.get("/companies", response_model=list[Company])
def list_companies(status: CompanyStatus | None = None):
    return companies.find(status)


@router.post("/companies", response_model=Ok)
def add_company(body: CompanyAdd):
    if not service.add(body.name, body.email, body.position):
        raise HTTPException(400, "Неверный email или он уже есть в списке")
    return Ok()


@router.post("/companies/import", response_model=Added)
async def import_companies(file: UploadFile = File(...)):
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(400, "Файл больше 5 МБ")
    try:
        return Added(added=service.import_file(file.filename or "", raw))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.patch("/companies/status", response_model=Ok)
def change_company_status(body: CompanyStatusChange):
    companies.set_status(body.ids, body.status)
    return Ok()


@router.post("/companies/delete", response_model=Ok)
def delete_companies(body: Ids):
    companies.delete(body.ids)
    return Ok()


@router.patch("/companies/{cid}", response_model=Ok)
def update_company(cid: int, body: CompanyUpdate):
    if not companies.update(cid, body.name, body.position):
        raise HTTPException(404, "Компания не найдена")
    return Ok()


@router.get("/companies/{cid}/preview", response_model=MailPreview)
def mail_preview(cid: int):
    c = companies.get(cid)
    if not c:
        raise HTTPException(404, "Компания не найдена")
    return mailer.preview(settings.get(), c)


@router.post("/mail/test", response_model=MailTest)
def mail_test():
    ok, text = mailer.test_connection()
    return MailTest(ok=ok, message=text)
