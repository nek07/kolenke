"""What the «Сегодня» screen and the header show, global search and statistics."""
from kolenke.db.repositories import chats, companies, stats, vacancies
from kolenke.db.repositories.events import recent_log
from kolenke.services import pipeline
from kolenke.services.text import norm, week_start
from kolenke.workers import scheduler
from kolenke.workers.runner import runner


def status() -> dict:
    next_run = scheduler.state.next_run
    return {
        "running": runner.running,
        "job": runner.name if runner.running else None,
        "log": recent_log(),
        "vacancies": vacancies.count_by_status(),
        "companies": companies.count_by_status(),
        "applied_today": vacancies.applied_today_hh(),
        "week": stats.week(week_start()),
        "review": vacancies.count("source='hh' AND status='new'"),
        "sent_today": companies.sent_today(),
        "chats_pending": chats.count("pending"),
        "attention": vacancies.count("status='attention'"),
        "reminders": pipeline.due_today_count(),
        "no_letter": vacancies.count("status='applied' AND letter_sent=0"),
        "autopilot_next": next_run.strftime("%H:%M") if next_run else None,
    }


def statistics() -> dict:
    return {"by_day": stats.by_day(), "hh_states": stats.hh_states(), "by_resume": stats.by_resume(),
            "skipped": stats.skip_reasons()}


def search(q: str) -> dict:
    """One box for everything a company can show up in: vacancies on all sites, employer chats, the mail list.
    Filtered in Python: SQLite LIKE only ignores case for Latin letters, and most names here are Cyrillic."""
    words = norm(q).split()
    if not words:
        return {"vacancies": [], "chats": [], "companies": []}

    def hit(*fields):
        text = norm(" ".join(f or "" for f in fields))
        return all(w in text for w in words)

    found_chats, seen = [], set()
    for c in chats.visible_newest_first():
        if c["chat_id"] not in seen and hit(c["company"], c["vacancy"], c["message"]):
            seen.add(c["chat_id"])  # one row per chat, its latest message
            found_chats.append(c)
    return {
        "vacancies": [v for v in vacancies.all_for_search() if hit(v["title"], v["company"])][:20],
        "chats": found_chats[:10],
        "companies": [c for c in companies.all_for_search() if hit(c["name"], c["email"], c["position"])][:10],
    }
