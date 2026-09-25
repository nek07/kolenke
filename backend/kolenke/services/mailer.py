"""Sending resume emails to companies through the user's own Gmail (SMTP + app password)."""
import mimetypes
import random
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from kolenke.db.repositories import companies, settings
from kolenke.db.repositories.events import log
from kolenke.schemas.settings import AppSettings
from kolenke.services.text import fill
from kolenke.workers.runner import runner


def _smtp(s: AppSettings) -> smtplib.SMTP_SSL:
    server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ssl.create_default_context(), timeout=30)
    server.login(s.smtp_user, s.smtp_password.replace(" ", ""))
    return server


def test_connection() -> tuple[bool, str]:
    try:
        _smtp(settings.get()).quit()
        return True, "Подключение к почте работает"
    except Exception as e:
        return False, f"Ошибка подключения: {e}"


def build(s: AppSettings, company: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{s.full_name} <{s.smtp_user}>" if s.full_name else s.smtp_user
    msg["To"] = company["email"]
    msg["Subject"] = fill(s.mail_subject_template, s, company["name"], company["position"])
    msg.set_content(fill(s.mail_body_template, s, company["name"], company["position"]))
    resume = Path(s.resume_file) if s.resume_file else None
    if resume and resume.exists():
        ctype = mimetypes.guess_type(resume.name)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(resume.read_bytes(), maintype=maintype, subtype=subtype, filename=resume.name)
    return msg


def preview(s: AppSettings, company: dict) -> dict:
    msg = build(s, company)
    body = msg.get_body(("plain",)).get_content() if msg.is_multipart() else msg.get_content()
    files = [p.get_filename() for p in msg.iter_attachments()] if msg.is_multipart() else []
    return {"to": msg["To"], "subject": msg["Subject"], "body": body, "attachments": files}


def send_queue() -> None:
    s = settings.get()
    if not s.smtp_user or not s.smtp_password:
        log("Почта: заполните Gmail и пароль приложения в настройках")
        return
    if not s.resume_file or not Path(s.resume_file).exists():
        log("Почта: сначала загрузите файл резюме")
        return
    queue = companies.queued()
    if not queue:
        log("Почта: очередь пуста")
        return
    dmin, dmax = s.mail_delay_min, max(s.mail_delay_min, s.mail_delay_max)
    server = _smtp(s)
    try:
        for i, c in enumerate(queue):
            if runner.stop_requested:
                log("Остановлено пользователем")
                break
            if companies.sent_today() >= s.mail_daily_limit:
                log(f"Почта: достигнут дневной лимит ({s.mail_daily_limit}). Остальное завтра")
                break
            try:
                try:
                    server.send_message(build(s, c))
                except smtplib.SMTPServerDisconnected:
                    server = _smtp(s)
                    server.send_message(build(s, c))
                companies.mark_sent(c["id"])
                log(f"Почта: отправлено → {c['name'] or ''} <{c['email']}>")
            except Exception as e:
                companies.mark_error(c["id"], str(e))
                log(f"Почта: ошибка {c['email']}: {e}")
            if i < len(queue) - 1:
                runner.sleep(random.randint(dmin, dmax))
    finally:
        try:
            server.quit()
        except Exception:
            pass
    log("Почта: рассылка завершена")
