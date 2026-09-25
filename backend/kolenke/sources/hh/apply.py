"""Responding to hh vacancies from the queue: resume choice, employer questionnaire, cover letter."""
import random

from playwright.sync_api import Page

from kolenke.db.repositories import events, settings, vacancies
from kolenke.db.repositories.events import log
from kolenke.schemas.enums import VacancyStatus
from kolenke.services import answers, filters
from kolenke.services.text import fill, norm
from kolenke.sources.browser import screenshot, visible, wait_captcha
from kolenke.sources.hh.letters import send_to_vacancy_chat
from kolenke.sources.hh.session import logged_in_page
from kolenke.workers.runner import runner

SUCCESS_MARKERS = [
    '[data-qa="vacancy-response-link-view-topic"]',
    'text=Резюме доставлено',
    'text=Вы откликнулись',
    'text=Отклик отправлен',
]
RESPOND_BUTTON = '[data-qa="vacancy-response-link-top"]'
RELOCATION_CONFIRM = '[data-qa="relocation-warning-confirm"]'
SUBMIT = '[data-qa="vacancy-response-submit-popup"]'
LETTER_TOGGLE = '[data-qa="vacancy-response-letter-toggle"]'
LETTER_BOX = '[data-qa="vacancy-response-popup-form-letter-input"]'
LETTER_SEND = '[data-qa="vacancy-response-letter-submit"]'
ALREADY_APPLIED = "отклик уже был"
DEFAULT_RESUME = "по умолчанию на hh"


def _pick_resume(page: Page, resume_hash: str, resume_title: str) -> bool:
    for sel in (f'input[value="{resume_hash}"]', f'[data-qa*="{resume_hash}"]'):
        if page.locator(sel).count():
            try:
                page.locator(sel).first.check(force=True) if "input" in sel else page.locator(sel).first.click()
                return True
            except Exception:
                pass
    popup = page.locator('[data-qa="vacancy-response-popup"], [role="dialog"]').first
    if resume_title and popup.count():
        opt = popup.get_by_text(resume_title, exact=True)
        if opt.count():
            try:
                opt.first.click()
                return True
            except Exception:
                pass
    return False


def _fill_questionnaire(page: Page, given: list[dict]) -> list[str]:
    """Fills employer questions from the answer base, appends {q, a} to given; returns the unanswered questions."""
    missing = []
    tasks = page.locator('[data-qa="task-body"]')
    for i in range(tasks.count()):
        t = tasks.nth(i)
        qel = t.locator('[data-qa="task-question"]')
        question = (qel.first.inner_text() if qel.count() else t.inner_text()).strip()
        _, ans = answers.match(question)
        choices = t.locator('input[type="radio"], input[type="checkbox"]')
        fields = t.locator('textarea, input[type="text"]')
        done = False
        if ans and choices.count():
            for j in range(choices.count()):
                c = choices.nth(j)
                label = (c.evaluate("e => (e.closest('label') || e.parentElement).innerText") or "").strip().lower()
                if label and (ans.lower() in label or label in ans.lower()):
                    c.check(force=True)
                    done = True
                    break
        elif ans and fields.count():
            fields.first.fill(ans)
            done = True
        if done:
            given.append({"q": question, "a": ans})
        else:
            missing.append(question)
            answers.remember_unknown(question, "form")
    return missing


def _attach_letter_after_response(page: Page, letter: str) -> bool:
    """hh often sends the response in one click; the letter is then added via «Приложить сопроводительное письмо»."""
    if not visible(page, LETTER_BOX, timeout=500):
        if not visible(page, LETTER_TOGGLE, timeout=5000):
            return False
        page.locator(LETTER_TOGGLE).first.click()
    if not visible(page, LETTER_BOX, timeout=3000):
        return False
    page.locator(LETTER_BOX).first.fill(letter)
    if not visible(page, LETTER_SEND, timeout=2000):
        return False
    page.locator(LETTER_SEND).first.click()
    page.wait_for_timeout(2500)
    return not visible(page, LETTER_BOX)  # the form disappears once the letter is sent


def apply_one(page: Page, domain: str, v: dict, letter: str, resume_hash: str = "",
              resume_title: str = "") -> tuple[str, str | None, dict]:
    """Returns (status, note, info) where info = {"letter": bool, "letter_via": "form"/"chat"/None,
    "resume": title when hh let us choose it, "form": [{q, a}]}."""
    info = {"letter": False, "letter_via": None, "resume": None, "form": []}
    page.goto(f"https://{domain}/vacancy/{v['ext_id']}", wait_until="domcontentloaded")
    if not wait_captcha(page):
        return VacancyStatus.error, "капча", info
    page.wait_for_timeout(1200)

    if visible(page, SUCCESS_MARKERS[0]):
        return VacancyStatus.applied, ALREADY_APPLIED, info

    if not visible(page, RESPOND_BUTTON, timeout=5000):
        return VacancyStatus.skipped, "нет кнопки отклика (архив или внешний сайт)", info
    page.locator(RESPOND_BUTTON).first.click()
    page.wait_for_timeout(2000)

    if visible(page, RELOCATION_CONFIRM):
        page.locator(RELOCATION_CONFIRM).first.click()
        page.wait_for_timeout(1500)

    if "vacancy_response" in page.url or visible(page, SUBMIT, timeout=1500):
        # a form before sending: questionnaire and/or resume choice; the letter goes with the response
        if resume_hash and _pick_resume(page, resume_hash, resume_title):
            info["resume"] = resume_title
        missing = _fill_questionnaire(page, info["form"])
        if missing:
            return VacancyStatus.attention, "анкета, нет ответа на: " + "; ".join(q[:80] for q in missing), info
        if letter:
            if not visible(page, LETTER_BOX, timeout=500) and visible(page, LETTER_TOGGLE):
                page.locator(LETTER_TOGGLE).first.click()
            if visible(page, LETTER_BOX, timeout=2000):
                page.locator(LETTER_BOX).first.fill(letter)
                info["letter"], info["letter_via"] = True, "form"
        if visible(page, SUBMIT):
            page.locator(SUBMIT).first.click()
            page.wait_for_timeout(2500)

    if not any(visible(page, m, timeout=3000 if i == 0 else 0) for i, m in enumerate(SUCCESS_MARKERS)):
        shot = screenshot(page, f"hh_{v['ext_id']}.png")
        return VacancyStatus.error, f"не удалось подтвердить отклик, скриншот: {shot}", info

    # one-click response: attach the letter right after it, or send it to the chat
    if letter and not info["letter"]:
        info["letter"] = _attach_letter_after_response(page, letter)
        info["letter_via"] = "form" if info["letter"] else None
        if not info["letter"]:
            try:
                info["letter"] = send_to_vacancy_chat(page, domain, letter, v["title"], v["company"])
            except Exception:
                info["letter"] = False
            info["letter_via"] = "chat" if info["letter"] else None
    return VacancyStatus.applied, None if info["letter"] or not letter else "отклик ушёл, но письмо приложить не удалось", info


def _record(v: dict, status: str, note: str | None, info: dict, letter: str) -> None:
    applied = status == VacancyStatus.applied and note != ALREADY_APPLIED
    resume = info["resume"] or DEFAULT_RESUME
    vacancies.save_apply_result(v["id"], status, note, applied, resume, letter, info["letter"], info["form"])
    if applied:
        events.add(v["id"], "applied", f"Отклик отправлен с резюме «{resume}»")
        if info["form"]:
            events.add(v["id"], "form", f"Анкета заполнена из базы ответов: {len(info['form'])} вопр.")
        if info["letter"]:
            events.add(v["id"], "letter", "Письмо приложено к отклику" if info["letter_via"] == "form" else "Письмо отправлено в чат вакансии")
        elif letter:
            events.add(v["id"], "error", "Письмо приложить не удалось")
    elif note == ALREADY_APPLIED:
        events.add(v["id"], "applied", "Отклик уже был сделан раньше")
    else:
        kind = {VacancyStatus.attention: "attention", VacancyStatus.error: "error"}.get(status, "skipped")
        text = {VacancyStatus.attention: "Нужны ваши ответы на анкету", VacancyStatus.skipped: "Пропущена"}.get(status, "Ошибка")
        events.add(v["id"], kind, text + (f": {note}" if note else ""))
    human = {VacancyStatus.applied: "отклик отправлен", VacancyStatus.skipped: "пропущена",
             VacancyStatus.attention: "нужны ответы на анкету", VacancyStatus.error: "ошибка"}
    extra = " + письмо ✓" if applied and info["letter"] else ""
    log(f"hh: {v['title']} — {v['company']}: {human.get(status, status)}{extra}{' (' + note + ')' if note else ''}")


def apply_queue() -> None:
    s = settings.get()
    queue = vacancies.apply_queue(s.f_sort_match)
    if not queue:
        log("hh: очередь пуста — отметьте вакансии и нажмите «В очередь»")
        return
    rejected = filters.rejected_if_enabled(s)
    pause_lo, pause_hi = s.hh_pause_min, max(s.hh_pause_min, s.hh_pause_max)
    log(f"hh: отклики пойдут с резюме «{s.resume_title or 'первое в списке hh'}»")
    with logged_in_page() as session:
        if not session:
            return
        page, domain = session
        for v in queue:
            if runner.stop_requested:
                log("Остановлено пользователем")
                break
            if vacancies.applied_today_hh() >= s.hh_daily_limit:
                log(f"hh: достигнут дневной лимит ({s.hh_daily_limit}). Остальное завтра")
                break
            if v["company"] and norm(v["company"]) in rejected:  # the refusal may have come after it was queued
                note = "эта компания уже отказала вам раньше"
                vacancies.skip(v["id"], note)
                events.add(v["id"], "filtered", f"Не откликаюсь: {note}")
                continue
            letter = fill(s.hh_letter_template, s, v["company"], v["title"])
            info = {"letter": False, "letter_via": None, "resume": None, "form": []}
            try:
                status, note, info = apply_one(page, domain, v, letter, s.hh_resume_hash, s.resume_title)
            except Exception as e:  # keep going on single failures
                status, note = VacancyStatus.error, str(e)[:300]
            _record(v, status, note, info, letter)
            page.wait_for_timeout(random.randint(pause_lo, pause_hi) * 1000)
    log("hh: обработка очереди завершена")
