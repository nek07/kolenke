import csv
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import autopilot
import chat_bot
import db
import hh_bot
import pipeline
import mailer
from jobs import job

db.init()
app = FastAPI(title="JobBot")
if not os.environ.get("JOBBOT_NO_BACKGROUND"):  # tests run without the scheduler
    autopilot.start()

LOCAL_HOSTS = {"127.0.0.1", "localhost"}


@app.middleware("http")
async def local_only(request: Request, call_next):
    """The server acts on your hh account and Gmail, so only JobBot's own page may use it:
    - Host must be localhost (blocks DNS-rebinding pages from reading data);
    - state-changing requests need the X-JobBot header, which other sites can't send without a CORS preflight
      that this server never allows (blocks cross-site «click here» requests)."""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if host not in LOCAL_HOSTS:
        return JSONResponse({"detail": "Доступ только с этого компьютера"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if request.headers.get("x-jobbot") != "1" or (origin and origin.split("//")[-1].rsplit(":", 1)[0] not in LOCAL_HOSTS):
            return JSONResponse({"detail": "Запрос отклонён"}, status_code=403)
    return await call_next(request)
STATIC = Path(__file__).parent / "static"
RESUME_DIR = db.DATA_DIR / "resume"
RESUME_DIR.mkdir(exist_ok=True)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


# ---------- settings ----------
@app.get("/api/settings")
def get_settings():
    s = db.get_settings()
    s["has_password"] = bool(s.pop("smtp_password"))
    s["resume_name"] = Path(s["resume_file"]).name if s["resume_file"] else ""
    return s


@app.post("/api/settings")
def save_settings(data: dict):
    if not data.get("smtp_password"):
        data.pop("smtp_password", None)  # keep the stored one
    data.pop("resume_file", None)
    db.set_settings(data)
    return {"ok": True}


@app.post("/api/resume")
async def upload_resume(file: UploadFile = File(...)):
    name = Path(file.filename).name
    if not name.lower().endswith((".pdf", ".doc", ".docx")):
        raise HTTPException(400, "Нужен PDF, DOC или DOCX")
    path = RESUME_DIR / name
    path.write_bytes(await file.read())
    db.set_settings({"resume_file": str(path)})
    return {"ok": True, "name": name}


# ---------- vacancies ----------
@app.get("/api/vacancies")
def vacancies(source: str = "", status: str = ""):
    sql, args = "SELECT * FROM vacancies WHERE 1=1", []
    if source:
        sql += " AND source=?"; args.append(source)
    if status:
        sql += " AND status=?"; args.append(status)
    return db.q(sql + " ORDER BY id DESC LIMIT 2000", args)


@app.post("/api/vacancies/add")
def add_vacancy(data: dict):
    url = (data.get("url") or "").strip()
    if not url.startswith("http"):
        raise HTTPException(400, "Нужна ссылка на вакансию")
    db.x(
        "INSERT OR IGNORE INTO vacancies(source, url, title, company, status, created_at) VALUES (?, ?, ?, ?, 'new', ?)",
        (data.get("source") or "other", url, data.get("title") or url, data.get("company") or "", db.now()),
    )
    return {"ok": True}


STATUS_EVENTS = {"queued": "Вы добавили в очередь на отклик", "skipped": "Вы пропустили", "new": "Вы вернули в новые",
                 "applied": "Вы отметили: откликнулись", "attention": "Отмечена как требующая ответа"}


@app.post("/api/vacancies/status")
def vacancies_status(data: dict):
    ids, status, review = data.get("ids") or [], data.get("status"), bool(data.get("review"))
    if status not in ("new", "queued", "applied", "skipped", "attention"):
        raise HTTPException(400)
    for i in ids:
        db.x("UPDATE vacancies SET status=?, applied_at=CASE WHEN ?='applied' THEN ? ELSE applied_at END, "
             "reviewed_at=CASE WHEN ? THEN ? ELSE reviewed_at END WHERE id=?",
             (status, status, db.now(), review, db.now(), i))
        text = STATUS_EVENTS[status]
        if review:
            text = {"queued": "Вы одобрили при проверке: «Откликнуться»", "skipped": "Вы пропустили при проверке"}.get(status, text)
        db.event(i, status, text)
    return {"ok": True}


@app.post("/api/vacancies/queue_all_new")
def queue_all_new(data: dict):
    rows = db.q("SELECT id FROM vacancies WHERE status='new' AND source=?", (data.get("source") or "hh",))
    for r in rows:
        db.x("UPDATE vacancies SET status='queued' WHERE id=?", (r["id"],))
        db.event(r["id"], "queued", "Вы добавили в очередь («Все новые в очередь»)")
    return {"ok": True, "count": len(rows)}


@app.get("/api/review")
def review():
    """New hh vacancies waiting for «Откликнуться» / «Пропустить», best skill match first."""
    order = "skill_match IS NULL, skill_match DESC, id DESC" if db.get_settings()["f_sort_match"] == "1" else "id DESC"
    return db.q(f"SELECT * FROM vacancies WHERE source='hh' AND status='new' ORDER BY {order} LIMIT 300")


@app.get("/api/vacancies/{vid}")
def vacancy_detail(vid: int):
    import filters
    rows = db.q("SELECT * FROM vacancies WHERE id=?", (vid,))
    if not rows:
        raise HTTPException(404)
    v = rows[0]
    # chats keep the company and (not always) the vacancy title: match the company, and when the chat names
    # another known vacancy of this company, it belongs to that one
    words = [w for w in filters.norm(v["company"]).split() if len(w) > 3 and w not in ("тоо", "филиал")]
    same_company = lambda company: bool(words) and any(w in filters.norm(company) for w in words)
    siblings = {filters.norm(r["title"]) for r in db.q("SELECT title, company FROM vacancies WHERE source='hh' AND id != ?", (vid,))
                if same_company(r["company"])} - {filters.norm(v["title"])}

    def belongs(c):
        if c["vacancy"] == v["title"]:
            return True
        if not same_company(c["company"]) or filters.norm(c["vacancy"]) in siblings:
            return False
        text = filters.norm(c["message"])
        if filters.norm(v["title"]) in text:
            return True
        return not siblings  # the chat doesn't say which vacancy: only safe when it is the company's only one

    chats = [c for c in db.q("SELECT * FROM chat_items WHERE status != 'hidden' ORDER BY id") if belongs(c)]
    return {
        **v,
        "match_info": json.loads(v["match_info"] or "[]"),
        "form_answers": json.loads(v["form_answers"] or "[]"),
        "events": db.q("SELECT ts, kind, text FROM events WHERE vacancy_id=? ORDER BY id", (vid,)),
        "chats": chats,
    }


# ---------- pipeline (after the response) ----------
@app.get("/api/pipeline")
def get_pipeline():
    pipeline.ensure_stages()
    return {
        "stages": [{"id": s, "label": pipeline.LABELS[s]} for s in pipeline.STAGES],
        "cards": db.q(
            "SELECT id, source, url, title, company, stage, stage_manual, stage_at, notes, next_step, next_at, "
            "hh_state, applied_at, created_at, followup FROM vacancies WHERE status='applied' "
            "ORDER BY COALESCE(next_at, '9999'), COALESCE(stage_at, applied_at, created_at) DESC"
        ),
    }


@app.post("/api/vacancies/{vid}/pipeline")
def set_pipeline(vid: int, data: dict):
    try:
        v = pipeline.update(vid, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not v:
        raise HTTPException(404)
    return v


@app.get("/api/reminders")
def get_reminders():
    return pipeline.reminders()


@app.post("/api/vacancies/{vid}/followup")
def followup(vid: int, data: dict):
    action = data.get("action")
    if action == "send":
        text = (data.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "Пустое сообщение")
        db.x("UPDATE vacancies SET followup='approved', followup_text=? WHERE id=?", (text, vid))
        started = job.start("Напоминания о себе", hh_bot.send_followups)
        return {"ok": True, "started": started}
    if action in ("done", "dismissed"):
        db.x("UPDATE vacancies SET followup=?, followup_at=? WHERE id=?", (action, db.now(), vid))
        return {"ok": True}
    raise HTTPException(400)


@app.get("/api/vacancies/{vid}/followup_draft")
def followup_draft(vid: int):
    v = db.q("SELECT title, company FROM vacancies WHERE id=?", (vid,))
    if not v:
        raise HTTPException(404)
    return {"text": db.fill(db.get_settings()["followup_template"], company=v[0]["company"], position=v[0]["title"])}


@app.post("/api/vacancies/delete")
def vacancies_delete(data: dict):
    for i in data.get("ids") or []:
        db.x("DELETE FROM vacancies WHERE id=?", (i,))
    return {"ok": True}


# ---------- companies ----------
@app.get("/api/companies")
def companies(status: str = ""):
    if status:
        return db.q("SELECT * FROM companies WHERE status=? ORDER BY id DESC", (status,))
    return db.q("SELECT * FROM companies ORDER BY id DESC")


def _add_company(name, email, position):
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return 0
    return db.x(
        "INSERT OR IGNORE INTO companies(name, email, position, created_at) VALUES (?, ?, ?, ?)",
        ((name or "").strip(), email, (position or "").strip(), db.now()),
    )


def _read_rows(filename: str, raw: bytes):
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        return [["" if c is None else str(c) for c in row] for row in wb.active.iter_rows(values_only=True)]
    text = raw.decode("utf-8-sig", errors="ignore")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def _col(header, *names):
    for i, h in enumerate(header):
        if any(n in h for n in names):
            return i
    return None


@app.post("/api/companies/import")
async def import_companies(file: UploadFile = File(...)):
    rows = [r for r in _read_rows(file.filename, await file.read()) if any(c.strip() for c in r)]
    if not rows:
        raise HTTPException(400, "Файл пустой")
    header = [c.strip().lower() for c in rows[0]]
    ci = _col(header, "компан", "company", "назван", "name", "организ", "банк")
    ei = _col(header, "email", "e-mail", "почт", "mail")
    pi = _col(header, "должн", "позиц", "position", "ваканс")
    has_header = ei is not None and not EMAIL_RE.search(rows[0][ei] if ei < len(rows[0]) else "")
    added = 0
    for row in rows[1:] if has_header else rows:
        cell = lambda i: row[i] if i is not None and i < len(row) else ""
        emails = EMAIL_RE.findall(cell(ei)) if has_header else []
        if not emails:
            emails = [e for c in row for e in EMAIL_RE.findall(c)]
        name = cell(ci) if has_header else next((c for c in row if c.strip() and not EMAIL_RE.search(c)), "")
        for e in emails:
            added += _add_company(name, e, cell(pi) if has_header else "")
    return {"ok": True, "added": added}


@app.post("/api/companies/add")
def add_company(data: dict):
    if not _add_company(data.get("name"), data.get("email") or "", data.get("position")):
        raise HTTPException(400, "Неверный email или он уже есть в списке")
    return {"ok": True}


@app.post("/api/companies/update")
def update_company(data: dict):
    db.x("UPDATE companies SET name=?, position=? WHERE id=?", (data.get("name"), data.get("position"), data["id"]))
    return {"ok": True}


@app.post("/api/companies/status")
def companies_status(data: dict):
    status = data.get("status")
    if status not in ("new", "queued", "sent"):
        raise HTTPException(400)
    for i in data.get("ids") or []:
        db.x("UPDATE companies SET status=? WHERE id=?", (status, i))
    return {"ok": True}


@app.post("/api/companies/delete")
def companies_delete(data: dict):
    for i in data.get("ids") or []:
        db.x("DELETE FROM companies WHERE id=?", (i,))
    return {"ok": True}


@app.get("/api/companies/{cid}/preview")
def preview(cid: int):
    rows = db.q("SELECT * FROM companies WHERE id=?", (cid,))
    if not rows:
        raise HTTPException(404)
    msg = mailer.build(db.get_settings(), rows[0])
    body = msg.get_body(("plain",)).get_content() if msg.is_multipart() else msg.get_content()
    files = [p.get_filename() for p in msg.iter_attachments()] if msg.is_multipart() else []
    return {"to": msg["To"], "subject": msg["Subject"], "body": body, "attachments": files}


@app.post("/api/mail/test")
def mail_test():
    ok, text = mailer.test_connection()
    return {"ok": ok, "message": text}


# ---------- jobs ----------
JOBS = {
    "hh_login": ("Вход в hh", hh_bot.login),
    "hh_check": ("Проверка входа hh", hh_bot.check_login),
    "hh_resumes": ("Загрузка резюме hh", hh_bot.load_resumes),
    "hh_search": ("Поиск вакансий hh", hh_bot.search),
    "hh_apply": ("Отклики hh", hh_bot.apply_queue),
    "hh_sync": ("Статусы откликов hh", hh_bot.sync_responses),
    "hh_letters": ("Письма к откликам", hh_bot.send_missing_letters),
    "hh_followups": ("Напоминания о себе", hh_bot.send_followups),
    "chat_check": ("Чаты hh", chat_bot.run),
    "autopilot_now": ("Автопилот", autopilot.cycle),
    "mail_send": ("Рассылка резюме", mailer.send_queue),
}


@app.post("/api/jobs/stop")
def stop_job():
    job.stop()
    return {"ok": True}


@app.post("/api/jobs/{name}")
def start_job(name: str):
    if name not in JOBS:
        raise HTTPException(404)
    title, fn = JOBS[name]
    if not job.start(title, fn):
        raise HTTPException(409, f"Уже выполняется: {job.name}")
    db.log(f"▶ {title}")
    return {"ok": True}


def _reminder_count():
    r = pipeline.reminders()
    today_end = datetime.now().replace(hour=23, minute=59).isoformat(timespec="seconds")
    return len(r["followups"]) + len(r["past"]) + sum(1 for u in r["upcoming"] if u["next_at"] <= today_end)


def week_stats():
    """The main metric: invitations this week and the share of responses that end with an invitation."""
    ws = db.week_start()
    inv = ",".join("?" * len(db.INVITE_STATES))
    applied_all = db.q("SELECT COUNT(*) n FROM vacancies WHERE source='hh' AND status='applied'")[0]["n"]
    invites_all = db.q(f"SELECT COUNT(*) n FROM vacancies WHERE source='hh' AND hh_state IN ({inv})", db.INVITE_STATES)[0]["n"]
    return {
        "start": ws,
        "invites": db.q("SELECT COUNT(*) n FROM vacancies WHERE source='hh' AND invited_at >= ?", (ws,))[0]["n"],
        "applied": db.q("SELECT COUNT(*) n FROM vacancies WHERE source='hh' AND status='applied' AND applied_at >= ?", (ws,))[0]["n"],
        "applied_all": applied_all,
        "invites_all": invites_all,
        "rate": round(invites_all * 100 / applied_all, 1) if applied_all else None,
    }


@app.get("/api/status")
def status():
    counts = lambda t: {r["status"]: r["n"] for r in db.q(f"SELECT status, COUNT(*) n FROM {t} GROUP BY status")}
    return {
        "running": job.running,
        "job": job.name if job.running else None,
        "log": db.q("SELECT ts, msg FROM log ORDER BY id DESC LIMIT 80"),
        "vacancies": counts("vacancies"),
        "companies": counts("companies"),
        "applied_today": db.count_today("vacancies", "applied_at", "applied", "AND source='hh'"),
        "week": week_stats(),
        "review": db.q("SELECT COUNT(*) n FROM vacancies WHERE source='hh' AND status='new'")[0]["n"],
        "sent_today": db.count_today("companies", "sent_at", "sent"),
        "chats_pending": db.q("SELECT COUNT(*) n FROM chat_items WHERE status='pending'")[0]["n"],
        "attention": db.q("SELECT COUNT(*) n FROM vacancies WHERE status='attention'")[0]["n"],
        "reminders": _reminder_count(),
        "no_letter": db.q("SELECT COUNT(*) n FROM vacancies WHERE status='applied' AND letter_sent=0")[0]["n"],
        "autopilot_next": autopilot.state["next_run"].strftime("%H:%M") if autopilot.state["next_run"] else None,
    }


# ---------- chats & answer base ----------
@app.get("/api/chats")
def chats(status: str = "pending"):
    return db.q("SELECT * FROM chat_items WHERE status=? ORDER BY id DESC LIMIT 300", (status,))


@app.get("/api/chats/history")
def chats_history():
    return db.q("SELECT * FROM chat_items WHERE status IN ('sent','auto_sent','approved') ORDER BY id DESC LIMIT 300")


@app.post("/api/chats/{cid}")
def chat_action(cid: int, data: dict):
    action = data.get("action")
    if action == "send":
        reply = (data.get("reply") or "").strip()
        if not reply:
            raise HTTPException(400, "Пустой ответ")
        db.x("UPDATE chat_items SET status='approved', reply=? WHERE id=?", (reply, cid))
        started = job.start("Чаты hh", chat_bot.run)
        return {"ok": True, "started": started}
    if action == "hide":
        db.x("UPDATE chat_items SET status='hidden' WHERE id=?", (cid,))
        return {"ok": True}
    raise HTTPException(400)


@app.get("/api/answers")
def get_answers():
    return db.q("SELECT * FROM answers ORDER BY id")


@app.post("/api/answers")
def save_answers(data: dict):
    for a in data.get("items") or []:
        if a.get("id"):
            db.x("UPDATE answers SET topic=?, keywords=?, answer=? WHERE id=?", (a["topic"], a["keywords"], a["answer"], a["id"]))
        elif (a.get("topic") or a.get("keywords")):
            db.x("INSERT INTO answers(topic, keywords, answer) VALUES (?, ?, ?)", (a["topic"], a["keywords"], a["answer"]))
    return {"ok": True}


@app.post("/api/answers/delete")
def delete_answer(data: dict):
    db.x("DELETE FROM answers WHERE id=?", (data["id"],))
    return {"ok": True}


@app.get("/api/answers/test")
def test_answer(q: str):
    import answers
    topic, ans = answers.match(q)
    return {"topic": topic, "answer": ans}


@app.get("/api/questions")
def get_questions():
    return db.q("SELECT * FROM questions ORDER BY seen DESC, id DESC LIMIT 200")


@app.post("/api/questions/delete")
def delete_question(data: dict):
    db.x("DELETE FROM questions WHERE id=?", (data["id"],))
    return {"ok": True}


@app.get("/api/stats")
def stats():
    applied = "status='applied' AND source='hh'"
    return {
        "by_day": db.q(
            "SELECT d, SUM(hh) hh, SUM(mail) mail FROM ("
            " SELECT substr(applied_at,1,10) d, 1 hh, 0 mail FROM vacancies WHERE " + applied + " AND applied_at IS NOT NULL"
            " UNION ALL SELECT substr(sent_at,1,10), 0, 1 FROM companies WHERE status='sent'"
            ") GROUP BY d ORDER BY d DESC LIMIT 30"
        ),
        "hh_states": db.q(
            f"SELECT COALESCE(hh_state, 'не синхронизировано') state, COUNT(*) n FROM vacancies WHERE {applied} "
            "GROUP BY state ORDER BY n DESC"
        ),
        "by_resume": db.q(
            f"SELECT COALESCE(resume, 'вне бота / неизвестно') resume, COUNT(*) n, "
            "SUM(hh_state IN ('приглашение','собеседование','выход на работу')) invites, "
            "SUM(hh_state='отказ') discards FROM vacancies WHERE " + applied + " GROUP BY 1 ORDER BY n DESC"
        ),
        "skipped": db.q("SELECT note, COUNT(*) n FROM vacancies WHERE status IN ('skipped','error') GROUP BY note ORDER BY n DESC LIMIT 10"),
    }


EXPORTS = {
    "vacancies": ("otkliki.csv", "SELECT source AS Сайт, title AS Вакансия, company AS Компания, url AS Ссылка, "
                  "status AS Статус, salary_text AS Зарплата, skill_match AS Совпадение_навыков, resume AS Резюме, "
                  "hh_state AS Ответ_работодателя, applied_at AS Дата_отклика, "
                  "note AS Примечание FROM vacancies ORDER BY applied_at DESC, id DESC"),
    "companies": ("pisma.csv", "SELECT name AS Компания, email AS Email, position AS Должность, status AS Статус, "
                  "sent_at AS Дата_отправки, note AS Примечание FROM companies ORDER BY sent_at DESC, id DESC"),
}


@app.get("/api/export/{what}")
def export(what: str):
    if what not in EXPORTS:
        raise HTTPException(404)
    filename, sql = EXPORTS[what]
    rows = db.q(sql)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")  # ; so Excel with Russian locale splits columns
    w.writerow(rows[0].keys() if rows else ["нет данных"])
    w.writerows([list(r.values()) for r in rows])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
