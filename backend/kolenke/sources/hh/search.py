"""Finding hh vacancies: the list hh recommends for your resume, or a text search, through your smart filters."""
import random
import re
from urllib.parse import quote

from kolenke.db.repositories import events, settings, vacancies
from kolenke.db.repositories.events import log
from kolenke.schemas.enums import HhMode, VacancySource, VacancyStatus
from kolenke.services import filters
from kolenke.sources.browser import hh_window, screenshot, visible, wait_captcha
from kolenke.workers.runner import runner

# Reads a search results page. hh does not give the skill match a stable data-qa, so it is found by its text
# («Совпадение навыков 78%», «78% совпадение»...) anywhere in the card.
SERP_JS = """() => {
    const cards = document.querySelectorAll('[data-qa~="vacancy-serp__vacancy"]');
    const txt = (card, sel) => { const e = card.querySelector(sel); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : ''; };
    const out = [];
    cards.forEach(card => {
        const a = card.querySelector('a[data-qa="serp-item__title"]') || card.querySelector('a[href*="/vacancy/"]');
        if (!a) return;
        const t = card.querySelector('[data-qa="serp-item__title-text"]') || a;
        let salary = txt(card, '[data-qa="vacancy-serp__vacancy-compensation"]');
        if (!salary) {
            const line = card.innerText.split('\\n').find(l => /\\d/.test(l) && /[₸₽$€]|руб|тенге|KZT|RUR|USD/i.test(l));
            salary = line ? line.trim() : '';
        }
        let match = null;
        for (const line of card.innerText.split('\\n')) {
            if (!/%/.test(line) || !/навык|совпад|подход|match/i.test(line)) continue;
            const m = line.match(/(\\d{1,3})\\s*%/);
            if (m) { match = +m[1]; break; }
        }
        if (match === null) {
            const el = card.querySelector('[data-qa*="match" i], [data-qa*="skill" i], [class*="match" i]');
            const m = el && el.innerText.match(/(\\d{1,3})\\s*%/);
            if (m) match = +m[1];
        }
        out.push({
            href: a.href, title: t.innerText.trim(), company: txt(card, '[data-qa="vacancy-serp__vacancy-employer"]'),
            salary, experience: txt(card, '[data-qa^="vacancy-serp__vacancy-work-experience"]'), match,
        });
    });
    return out;
}"""


def _page_url(s, n: int, fresh: bool) -> str:
    base = f"https://{s.hh_domain}/search/vacancy?"
    if s.hh_mode == HhMode.resume:  # the same list hh shows as «подходящие вакансии» for the resume
        url = base + f"resume={s.hh_resume_hash}&page={n}&items_on_page=50"
    else:
        url = base + f"text={quote(s.hh_query.strip())}&page={n}&items_on_page=50"
    if s.hh_area.strip():
        url += f"&area={s.hh_area.strip()}"
    url += "".join(f"&experience={c}" for c in s.f_experience)
    if s.f_skip_no_salary:
        url += "&only_with_salary=true"
    if fresh:
        url += "&order_by=publication_time&search_period=1"
    return url


def search(fresh: bool = False) -> int | None:
    """fresh=True: only vacancies published in the last 24h, newest first (used by the autopilot).
    Returns how many new vacancies passed the filters."""
    s = settings.get()
    by_resume = s.hh_mode == HhMode.resume
    if by_resume and not s.hh_resume_hash:
        log("hh: выберите резюме (сначала «Проверить вход» — список резюме подтянется)")
        return None
    if not by_resume and not s.hh_query.strip():
        log("Укажите поисковый запрос для hh")
        return None
    source = f"найдена среди подходящих к резюме «{s.resume_title}»" if by_resume else f"найдена по запросу «{s.hh_query.strip()}»"
    if fresh:
        source += ", опубликована за последние сутки"
    rejected = filters.rejected_if_enabled(s)
    added = passed = with_match = 0
    with hh_window() as (_, page):
        for n in range(s.hh_pages):
            if runner.stop_requested:
                break
            page.goto(_page_url(s, n, fresh), wait_until="domcontentloaded")
            if not wait_captcha(page):
                break
            # results are rendered by JS: wait for cards instead of a fixed pause
            if not visible(page, 'a[data-qa="serp-item__title"]', timeout=15000):
                wait_captcha(page)
                if not visible(page, 'a[data-qa="serp-item__title"]', timeout=5000):
                    if n > 0:  # simply ran out of result pages
                        break
                    shot = screenshot(page, f"search_page{n + 1}.png")
                    log(f"hh: на странице {n + 1} нет вакансий (скриншот: {shot})")
                    break
            page.wait_for_timeout(800)
            items = page.evaluate(SERP_JS)
            if not items:
                log(f"hh: страница {n + 1} пустая, поиск завершён")
                break
            for it in items:
                m = re.search(r"/vacancy/(\d+)", it["href"])
                if not m:
                    continue
                lo, hi = filters.parse_salary(it["salary"])
                v = {
                    "source": VacancySource.hh, "ext_id": m.group(1), "url": f"https://{s.hh_domain}/vacancy/{m.group(1)}",
                    "title": it["title"].replace("\n", " "), "company": it["company"].replace("\n", " "),
                    "salary_text": it["salary"] or None, "salary_from": lo, "salary_to": hi,
                    "experience": it["experience"] or None, "skill_match": it["match"],
                }
                with_match += it["match"] is not None
                ok, note, reasons = filters.check(v, s, rejected, source)
                vid = vacancies.add_found(v, VacancyStatus.new if ok else VacancyStatus.skipped, note, reasons)
                if vid is None:
                    continue
                added += 1
                passed += ok
                events.add(vid, "found", source[0].upper() + source[1:])
                if not ok:
                    events.add(vid, "filtered", f"Отсеяна фильтром: {note}")
            log(f"hh: страница {n + 1} — найдено {len(items)} вакансий")
            page.wait_for_timeout(random.randint(1500, 3500))
    if added and not with_match:
        log("hh: на этих страницах hh не показал «совпадение навыков», сортировка по нему недоступна")
    log(f"hh: поиск завершён, новых вакансий: {added}, прошли фильтры: {passed}")
    return passed
