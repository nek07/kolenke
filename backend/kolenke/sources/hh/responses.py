"""Employer reactions from hh «Отклики», including responses you made by hand on the site."""
import random
import re

from kolenke.db.repositories import events, vacancies
from kolenke.db.repositories.events import log
from kolenke.services import pipeline
from kolenke.sources.browser import visible, wait_captcha
from kolenke.sources.hh.session import logged_in_page
from kolenke.workers.runner import runner

STATE_NAMES = {
    "not-viewed": "не просмотрен", "viewed": "просмотрен", "discard": "отказ",
    "invitation": "приглашение", "invite": "приглашение", "interview": "собеседование",
    "hired": "выход на работу", "archived": "в архиве",
}

NEGOTIATIONS_JS = """() => [...document.querySelectorAll('[data-qa="negotiations-item"]')].map(it => {
    const a = it.querySelector('a[href*="/vacancy/"]');
    const tag = it.querySelector('[data-qa^="negotiations-tag"]');
    const q = sel => { const e = it.querySelector(sel); return e ? e.innerText.trim() : ''; };
    return {
        href: a ? a.href : '',
        title: q('[data-qa="negotiations-item-vacancy"]'),
        company: q('[data-qa="negotiations-item-company"]'),
        date: q('[data-qa="negotiations-item-date"]'),
        state: tag ? tag.dataset.qa.replace('negotiations-tag', '').replace('negotiations-item-', '').trim() : '',
        state_text: tag ? tag.innerText.trim() : '',
    };
})"""


def _store(domain: str, it: dict) -> tuple[int, int]:
    """(updated, added) for one row of the responses list."""
    m = re.search(r"/vacancy/(\d+)", it["href"])
    if not m:
        return 0, 0
    ext_id = m.group(1)
    state = STATE_NAMES.get(it["state"]) or it["state_text"].lower() or it["state"]
    known = vacancies.get_by_ext_id("hh", ext_id)
    if known:
        updated = vacancies.set_hh_state(known["id"], state)
        if state != known["hh_state"]:
            events.add(known["id"], "employer", f"Работодатель: {state}")
        pipeline.ensure_stages()
        pipeline.advance_from_hh(known["id"], state)
        return updated, 0
    vid = vacancies.add_external_response(ext_id, f"https://{domain}/vacancy/{ext_id}", it["title"], it["company"],
                                          it["date"], state)
    if vid is None:
        return 0, 0
    events.add(vid, "applied", f"Отклик сделан вне бота ({it['date']})")
    events.add(vid, "employer", f"Работодатель: {state}")
    pipeline.ensure_stages()
    return 0, 1


def sync_responses() -> None:
    seen = updated = added = 0
    with logged_in_page() as session:
        if not session:
            return
        page, domain = session
        prev_first = None
        for n in range(50):
            if runner.stop_requested:
                break
            page.goto(f"https://{domain}/applicant/negotiations?filter=all&page={n}", wait_until="domcontentloaded")
            if not wait_captcha(page) or not visible(page, '[data-qa="negotiations-item"]', timeout=10000):
                break
            items = page.evaluate(NEGOTIATIONS_JS)
            if not items or items[0]["href"] == prev_first:
                break
            prev_first = items[0]["href"]
            for it in items:
                u, a = _store(domain, it)
                seen, updated, added = seen + 1, updated + u, added + a
            page.wait_for_timeout(random.randint(1200, 2500))
    log(f"hh: синхронизация откликов — всего {seen}, обновлено {updated}, добавлено {added}")
