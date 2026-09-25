"""Messages to the vacancy chat: cover letters that did not fit into the response, and follow-ups."""
import random

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from kolenke.db.repositories import events, settings, vacancies
from kolenke.db.repositories.events import log
from kolenke.schemas.enums import Followup
from kolenke.services.text import fill
from kolenke.sources.hh import chats
from kolenke.sources.hh.session import logged_in_page
from kolenke.workers.runner import runner

FIND_CHAT_JS = """([title, company]) => {
    const norm = s => (s || '').toLowerCase().replace(/[«»"]/g, '').replace(/\\s+/g, ' ').trim();
    const words = norm(company).split(' ').filter(w => w.length > 3 && !['филиал', 'акционерного', 'общества'].includes(w));
    const cells = [...document.querySelectorAll('[data-qa^="chatik-open-chat-"]')]
        .filter(e => norm(e.innerText.split('\\n')[0]) === norm(title));
    const hit = cells.find(e => words.some(w => norm(e.innerText).includes(w))) || cells[0];
    return hit ? hit.dataset.qa.replace('chatik-open-chat-', '') : null;
}"""


def _find_chat_id(page: Page, domain: str, title: str, company: str) -> str | None:
    """The «Чат» control on a vacancy page has no link, so find the chat by vacancy title in the chat list."""
    page.goto(f"https://{domain}/chat", wait_until="domcontentloaded")
    try:
        page.locator('[data-qa^="chatik-open-chat-"]').first.wait_for(timeout=15000)
    except PWTimeout:
        return None
    return page.evaluate(FIND_CHAT_JS, [title, company or ""])


def send_to_vacancy_chat(page: Page, domain: str, text: str, title: str, company: str) -> bool:
    cid = _find_chat_id(page, domain, title, company)
    if not cid:
        return False
    page.goto(f"https://{domain}/chat/{cid}", wait_until="domcontentloaded")
    return chats.read_chat(page) is not None and chats.send(page, text)


def send_missing_letters() -> None:
    """Send the cover letter to the chat for responses that went out without it."""
    rows = vacancies.missing_letters()
    if not rows:
        log("hh: все отклики уже с письмами")
        return
    s = settings.get()
    with logged_in_page() as session:
        if not session:
            return
        page, domain = session
        for v in rows:
            if runner.stop_requested:
                break
            letter = fill(s.hh_letter_template, s, v["company"], v["title"])
            ok = False
            try:
                ok = send_to_vacancy_chat(page, domain, letter, v["title"], v["company"])
            except Exception as e:
                log(f"hh: {v['title']}: ошибка {e}")
            if ok:
                vacancies.mark_letter_sent(v["id"], letter)
                events.add(v["id"], "letter", "Письмо дослано в чат вакансии")
            log(f"hh: письмо к «{v['title']}» — {v['company']}: {'отправлено в чат ✓' if ok else 'не удалось отправить'}")
            page.wait_for_timeout(random.randint(3000, 6000))


def send_followups() -> None:
    """Send the follow-ups you approved («напомнить о себе») to the vacancy chats."""
    rows = vacancies.approved_followups()
    if not rows:
        return
    with logged_in_page() as session:
        if not session:
            return
        page, domain = session
        for v in rows:
            if runner.stop_requested:
                break
            ok = False
            try:
                ok = send_to_vacancy_chat(page, domain, v["followup_text"], v["title"], v["company"])
            except Exception as e:
                log(f"hh: {v['title']}: ошибка {e}")
            if ok:
                vacancies.set_followup(v["id"], Followup.sent)
                events.add(v["id"], "followup", "Вы напомнили о себе в чате")
            log(f"hh: напоминание о себе — {v['company']}: {'отправлено ✓' if ok else 'не удалось, попробую позже'}")
            page.wait_for_timeout(random.randint(3000, 6000))
