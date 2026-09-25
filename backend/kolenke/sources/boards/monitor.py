"""Monitoring of the job boards: find vacancies, open new ones once, store them with contacts and filter reasons.
Contacts can later go to «Письма компаниям»."""
import random

from kolenke.db.repositories import events, settings, vacancies
from kolenke.db.repositories.events import log
from kolenke.schemas.enums import VacancyStatus
from kolenke.schemas.settings import AppSettings
from kolenke.services import filters
from kolenke.services.text import norm, split_list
from kolenke.sources import browser
from kolenke.sources.boards import REGISTRY
from kolenke.sources.boards.parsing import currency_of, merge_contacts
from kolenke.workers.runner import runner


def search_query(s: AppSettings) -> str:
    return (s.other_query or s.hh_query or s.desired_position).strip()  # a search phrase beats a job title


def evaluate(v: dict, s: AppSettings, rejected: set[str]) -> tuple[bool, str | None, list[dict]]:
    """Filters shared with hh + the place filter. Salary floors are in tenge: other currencies are not compared."""
    v["salary_from"], v["salary_to"] = filters.parse_salary(v.get("salary_text"))
    cur = currency_of(v.get("salary_text"))
    extra = []
    if v.get("salary_text") and cur and cur != "KZT" and s.f_salary_min:
        s = s.model_copy(update={"f_salary_min": None})
        extra.append({"ok": True, "text": f"зарплата в {cur}: фильтр «не ниже» в тенге не применялся"})
    board = REGISTRY.get(v["source"])
    ok, note, reasons = filters.check(v, s, rejected, f"найдена на {board.name if board else v['source']} по запросу «{search_query(s)}»")
    reasons += extra
    wanted = split_list(s.other_countries)  # countries and/or cities: «Казахстан», «астана», «удалённо»
    if wanted:
        where = norm(f"{v.get('country') or ''} {v.get('location') or ''}")
        good = any(w in where for w in wanted if "удал" not in w) or (v.get("remote") and any("удал" in w for w in wanted))
        place = ", ".join(x for x in (v.get("location"), v.get("country")) if x) or "место не указано"
        text = f"место: {place}" + (" (можно удалённо)" if v.get("remote") else "")
        reasons.append({"ok": bool(good), "text": text})
        if not good and ok:
            ok, note = False, f"{text} — не из вашего списка мест"
    return ok, note, reasons


def save(v: dict, ok: bool, note: str | None, reasons: list[dict]) -> bool:
    vid = vacancies.add_found(v, VacancyStatus.new if ok else VacancyStatus.skipped, note, reasons)
    if vid is None:
        return False
    board = REGISTRY.get(v["source"])
    events.add(vid, "found", f"Найдена на {board.name if board else v['source']}")
    if not ok:
        events.add(vid, "filtered", f"Отсеяна фильтром: {note}")
    return True


def monitor() -> int:
    """Search the chosen boards, open new vacancies once, store them. Returns how many passed the filters."""
    s = settings.get()
    query = search_query(s)
    boards = [REGISTRY[k] for k in s.other_sites if k in REGISTRY]
    if not query or not boards:
        log("Другие сайты: укажите запрос и хотя бы один сайт")
        return 0
    rejected = filters.rejected_if_enabled(s)
    known = vacancies.known_urls(list(REGISTRY))
    added = passed = details = 0
    cache: dict = {}
    with browser.headless_page() as page:
        for board in boards:
            if runner.stop_requested:
                break
            try:
                items = board.search(page, query, s.other_pages)
            except Exception as e:
                log(f"{board.name}: не удалось открыть поиск ({str(e)[:80]})")
                continue
            fresh = [v for v in items if v["ext_id"] and v["url"] not in known]
            log(f"{board.name}: найдено {len(items)}, новых {len(fresh)}")
            for v in fresh:
                if runner.stop_requested:
                    break
                v["contacts"], v["summary"] = merge_contacts(), ""
                if details < s.other_max_details:
                    try:
                        board.details(page, v, cache)
                        details += 1
                        page.wait_for_timeout(random.randint(800, 2000))
                    except Exception as e:  # one broken page must not stop the run
                        v["summary"] = f"Страницу вакансии открыть не удалось: {str(e)[:60]}"
                ok, note, reasons = evaluate(v, s, rejected)
                if save(v, ok, note, reasons):
                    added += 1
                    passed += ok
                    known.add(v["url"])
    left = " (остальные откроются в следующий раз)" if s.other_max_details and details >= s.other_max_details else ""
    log(f"Другие сайты: новых вакансий {added}, прошли фильтры {passed}{left}")
    return passed
