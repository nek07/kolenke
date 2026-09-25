"""Read-only aggregates for the dashboard, statistics and CSV exports."""
from kolenke.db.connection import placeholders, query, scalar
from kolenke.db.migrations import INVITE_STATES

_HH_APPLIED = "status='applied' AND source='hh'"


def week(start: str) -> dict:
    applied_all = scalar(f"SELECT COUNT(*) FROM vacancies WHERE {_HH_APPLIED}")
    invites_all = scalar(f"SELECT COUNT(*) FROM vacancies WHERE source='hh' AND hh_state IN ({placeholders(INVITE_STATES)})",
                         INVITE_STATES)
    return {
        "start": start,
        "invites": scalar("SELECT COUNT(*) FROM vacancies WHERE source='hh' AND invited_at >= ?", (start,)),
        "applied": scalar(f"SELECT COUNT(*) FROM vacancies WHERE {_HH_APPLIED} AND applied_at >= ?", (start,)),
        "applied_all": applied_all,
        "invites_all": invites_all,
        "rate": round(invites_all * 100 / applied_all, 1) if applied_all else None,
    }


def by_day(days: int = 30) -> list[dict]:
    return query(
        "SELECT d AS day, SUM(hh) hh, SUM(mail) mail FROM ("
        f" SELECT substr(applied_at,1,10) d, 1 hh, 0 mail FROM vacancies WHERE {_HH_APPLIED} AND applied_at IS NOT NULL"
        " UNION ALL SELECT substr(sent_at,1,10), 0, 1 FROM companies WHERE status='sent'"
        ") GROUP BY d ORDER BY d DESC LIMIT ?",
        (days,),
    )


def hh_states() -> list[dict]:
    return query(f"SELECT COALESCE(hh_state, 'не синхронизировано') state, COUNT(*) n FROM vacancies WHERE {_HH_APPLIED} "
                 "GROUP BY state ORDER BY n DESC")


def by_resume() -> list[dict]:
    return query(
        f"SELECT COALESCE(resume, 'вне бота / неизвестно') resume, COUNT(*) n, "
        f"SUM(hh_state IN ({placeholders(INVITE_STATES)})) invites, SUM(hh_state='отказ') discards "
        f"FROM vacancies WHERE {_HH_APPLIED} GROUP BY 1 ORDER BY n DESC",
        INVITE_STATES,
    )


def skip_reasons(limit: int = 10) -> list[dict]:
    return query("SELECT note, COUNT(*) n FROM vacancies WHERE status IN ('skipped','error') "
                 "GROUP BY note ORDER BY n DESC LIMIT ?", (limit,))


EXPORTS = {
    "vacancies": ("otkliki.csv", "SELECT source AS Сайт, title AS Вакансия, company AS Компания, url AS Ссылка, "
                  "status AS Статус, salary_text AS Зарплата, skill_match AS Совпадение_навыков, resume AS Резюме, "
                  "hh_state AS Ответ_работодателя, applied_at AS Дата_отклика, "
                  "note AS Примечание FROM vacancies ORDER BY applied_at DESC, id DESC"),
    "companies": ("pisma.csv", "SELECT name AS Компания, email AS Email, position AS Должность, status AS Статус, "
                  "sent_at AS Дата_отправки, note AS Примечание FROM companies ORDER BY sent_at DESC, id DESC"),
}


def export(what: str) -> tuple[str, list[dict]]:
    filename, sql = EXPORTS[what]
    return filename, query(sql)
