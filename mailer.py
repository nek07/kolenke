"""Sending resume emails to companies through the user's own Gmail (SMTP + app password)."""
import mimetypes
import random
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path

import db
from jobs import job


def _smtp(s):
    server = smtplib.SMTP_SSL(s["smtp_host"], int(s["smtp_port"]), context=ssl.create_default_context(), timeout=30)
    server.login(s["smtp_user"], s["smtp_password"].replace(" ", ""))
    return server


def test_connection():
    s = db.get_settings()
    try:
        _smtp(s).quit()
        return True, "Подключение к почте работает"
    except Exception as e:
        return False, f"Ошибка подключения: {e}"


def build(s, company):
    msg = EmailMessage()
    msg["From"] = f"{s['full_name']} <{s['smtp_user']}>" if s["full_name"] else s["smtp_user"]
    msg["To"] = company["email"]
    kw = dict(company=company["name"], position=company["position"] or "")
    msg["Subject"] = db.fill(s["mail_subject_template"], **kw)
    msg.set_content(db.fill(s["mail_body_template"], **kw))
    resume = Path(s["resume_file"]) if s["resume_file"] else None
    if resume and resume.exists():
        ctype = mimetypes.guess_type(resume.name)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(resume.read_bytes(), maintype=maintype, subtype=subtype, filename=resume.name)
    return msg


def send_queue():
    s = db.get_settings()
    if not s["smtp_user"] or not s["smtp_password"]:
        db.log("Почта: заполните Gmail и пароль приложения в настройках")
        return
    if not s["resume_file"] or not Path(s["resume_file"]).exists():
        db.log("Почта: сначала загрузите файл резюме")
        return
    limit = int(s["mail_daily_limit"] or 80)
    dmin, dmax = int(s["mail_delay_min"] or 40), int(s["mail_delay_max"] or 90)
    queue = db.q("SELECT * FROM companies WHERE status='queued' ORDER BY id")
    if not queue:
        db.log("Почта: очередь пуста")
        return
    server = _smtp(s)
    try:
        for i, c in enumerate(queue):
            if job.stop_requested:
                db.log("Остановлено пользователем")
                break
            if db.count_today("companies", "sent_at", "sent") >= limit:
                db.log(f"Почта: достигнут дневной лимит ({limit}). Остальное завтра")
                break
            try:
                try:
                    server.send_message(build(s, c))
                except smtplib.SMTPServerDisconnected:
                    server = _smtp(s)
                    server.send_message(build(s, c))
                db.x("UPDATE companies SET status='sent', note=NULL, sent_at=? WHERE id=?", (db.now(), c["id"]))
                db.log(f"Почта: отправлено → {c['name'] or ''} <{c['email']}>")
            except Exception as e:
                db.x("UPDATE companies SET status='error', note=? WHERE id=?", (str(e)[:300], c["id"]))
                db.log(f"Почта: ошибка {c['email']}: {e}")
            if i < len(queue) - 1:
                delay = random.randint(dmin, max(dmin, dmax))
                for _ in range(delay):
                    if job.stop_requested:
                        break
                    time.sleep(1)
    finally:
        try:
            server.quit()
        except Exception:
            pass
    db.log("Почта: рассылка завершена")
