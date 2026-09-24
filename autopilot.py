"""Autopilot: every N minutes find fresh vacancies for the resume, then either apply at once (auto)
or notify and let the user swipe through them (review), then handle hh chats."""
import threading
import time
from datetime import datetime, timedelta

import chat_bot
import db
import hh_bot
import other_sites
import pipeline
from jobs import job

state = {"last_run": None, "next_run": None}


def cycle():
    started = db.now()
    review = db.get_settings()["autopilot_mode"] != "auto"
    if review and db.q("SELECT 1 FROM vacancies WHERE source='hh' AND status='queued' LIMIT 1"):
        db.log("Автопилот: откликаюсь на вакансии, которые вы одобрили")
        hh_bot.apply_queue()  # what you approved in the review since the last cycle
    if job.stop_requested:
        return
    hh_bot.search(fresh=True)
    if job.stop_requested:
        return
    fresh = db.q("SELECT id FROM vacancies WHERE source='hh' AND status='new' AND created_at >= ?", (started,))
    if not fresh:
        db.log("Автопилот: новых вакансий нет")
    elif review:
        n = len(fresh)
        db.log(f"Автопилот: {n} новых подходящих вакансий ждут вашей проверки")
        chat_bot.notify(f"{n} новых подходящих вакансий. Пролистайте их в kolenke")
    else:
        for r in fresh:
            db.x("UPDATE vacancies SET status='queued' WHERE id=?", (r["id"],))
            db.event(r["id"], "queued", "Автопилот поставил в очередь")
        db.log(f"Автопилот: {len(fresh)} свежих вакансий — откликаюсь")
        hh_bot.apply_queue()
    if not job.stop_requested and db.get_settings()["other_monitor"] == "1":
        try:
            n = other_sites.monitor()
            if n:
                chat_bot.notify(f"{n} новых вакансий на Хабр Карьере и Enbek. Смотрите «Другие сайты»")
        except Exception as e:
            db.log(f"Другие сайты: ошибка {e}")
    if not job.stop_requested:
        try:  # a broken chat must not cancel the rest of the cycle
            chat_bot.run()
        except Exception as e:
            db.log(f"Чаты: ошибка {str(e)[:120]}")
    attention = db.q("SELECT COUNT(*) n FROM vacancies WHERE status='attention' AND applied_at IS NULL AND created_at >= ?", (started,))[0]["n"]
    if attention:
        chat_bot.notify(f"{attention} вакансий с анкетой ждут ваших ответов")


def _loop():
    while True:
        time.sleep(20)
        try:
            pipeline.notify_due(chat_bot.notify)
        except Exception as e:
            db.log(f"Напоминания: ошибка {e}")
        try:
            s = db.get_settings()
            if s["autopilot_on"] != "1":
                state["next_run"] = None
                continue
            now = datetime.now()
            if not int(s["autopilot_from"] or 0) <= now.hour < int(s["autopilot_to"] or 24):
                continue
            if state["next_run"] and now < state["next_run"]:
                continue
            if job.running:
                continue
            if job.start("Автопилот", cycle):
                db.log("▶ Автопилот")
                state["last_run"] = now
                state["next_run"] = now + timedelta(minutes=max(10, int(s["autopilot_interval"] or 30)))
        except Exception as e:
            db.log(f"Автопилот: ошибка планировщика {e}")


def start():
    threading.Thread(target=_loop, daemon=True).start()
