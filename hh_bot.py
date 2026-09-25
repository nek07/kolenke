"""HeadHunter automation through a real browser window with the user's own login session."""
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import answers
import db
import pipeline
from jobs import job

PROFILE_DIR = db.DATA_DIR / "browser_profile"
SCREENS_DIR = db.DATA_DIR / "screens"
SCREENS_DIR.mkdir(exist_ok=True)

SUCCESS_MARKERS = [
    '[data-qa="vacancy-response-link-view-topic"]',
    'text=Резюме доставлено',
    'text=Вы откликнулись',
    'text=Отклик отправлен',
]


def _open(p):
    ctx = p.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=False, viewport={"width": 1280, "height": 860}, locale="ru-RU"
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(15000)
    return ctx, page


def _visible(page, sel, timeout=0):
    try:
        loc = page.locator(sel).first
        if timeout:
            loc.wait_for(state="visible", timeout=timeout)
        return loc.is_visible()
    except PWTimeout:
        return False


def _wait_captcha(page):
    """If hh shows a captcha, wait for the user to solve it in the window."""
    if "captcha" not in page.url and not _visible(page, '[data-qa="account-captcha-input"]'):
        return True
    db.log("hh показал капчу — решите её в окне браузера, бот подождёт до 5 минут")
    for _ in range(150):
        if job.stop_requested:
            return False
        time.sleep(2)
        if "captcha" not in page.url and not _visible(page, '[data-qa="account-captcha-input"]'):
            db.log("Капча пройдена, продолжаю")
            return True
    return False


def is_logged_in(page, domain) -> bool:
    page.goto(f"https://{domain}/applicant/resumes", wait_until="domcontentloaded")
    return "login" not in page.url and "account" not in page.url


def login():
    s = db.get_settings()
    domain = s["hh_domain"]
    with sync_playwright() as p:
        ctx, page = _open(p)
        page.goto(f"https://{domain}/account/login", wait_until="domcontentloaded")
        db.log("Окно браузера открыто: войдите в свой аккаунт hh — окно закроется само после входа")
        closed = {"v": False}
        ctx.on("close", lambda *_: closed.update(v=True))
        for _ in range(600):  # up to 20 min
            if closed["v"] or job.stop_requested:
                break
            try:
                page.wait_for_timeout(2000)
                # hh sets hhrole=applicant once the job seeker is signed in
                if any(c["name"] == "hhrole" and c["value"] == "applicant" for c in ctx.cookies()):
                    db.log("hh: вход выполнен ✓")
                    _load_resumes(page, domain)
                    break
            except Exception:
                break
        if not closed["v"]:
            ctx.close()
    db.log("Окно входа закрыто. Сессия сохранена в профиле браузера")


def _load_resumes(page, domain):
    """Read the user's resumes from hh and remember them for the resume-based search."""
    page.goto(f"https://{domain}/applicant/resumes", wait_until="domcontentloaded")
    try:
        page.locator('a[data-qa^="resume-card-link-"]').first.wait_for(timeout=10000)
    except PWTimeout:
        db.log("hh: не нашёл резюме в аккаунте")
        return []
    resumes = page.evaluate(
        """() => [...document.querySelectorAll('a[data-qa^="resume-card-link-"]')].map(a => {
            const lines = a.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
            return {hash: a.dataset.qa.replace('resume-card-link-', ''), title: lines[1] || lines[0] || ''};
        })"""
    )
    s = db.get_settings()
    values = {"hh_resumes": json.dumps(resumes, ensure_ascii=False)}
    if resumes and s["hh_resume_hash"] not in [r["hash"] for r in resumes]:
        values["hh_resume_hash"] = resumes[0]["hash"]
    db.set_settings(values)
    db.log("hh: резюме в аккаунте: " + ", ".join(r["title"] for r in resumes))
    return resumes


def load_resumes():
    s = db.get_settings()
    with sync_playwright() as p:
        ctx, page = _open(p)
        if is_logged_in(page, s["hh_domain"]):
            _load_resumes(page, s["hh_domain"])
        else:
            db.log("hh: вы не вошли — нажмите «Войти в hh»")
        ctx.close()


def check_login():
    s = db.get_settings()
    with sync_playwright() as p:
        ctx, page = _open(p)
        ok = is_logged_in(page, s["hh_domain"])
        if ok:
            _load_resumes(page, s["hh_domain"])
        ctx.close()
    db.log("hh: вход выполнен ✓" if ok else "hh: вы не вошли — нажмите «Войти в hh»")
    return ok


EXPERIENCE_CODES = ("noExperience", "between1And3", "between3And6", "moreThan6")

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


def search(fresh=False):
    """fresh=True: only vacancies published in the last 24h, newest first (used by the autopilot)."""
    import filters  # local import keeps hh_bot importable on its own

    s = db.get_settings()
    domain, query = s["hh_domain"], s["hh_query"].strip()
    by_resume = s["hh_mode"] == "resume"
    if by_resume and not s["hh_resume_hash"]:
        db.log("hh: выберите резюме (сначала «Проверить вход» — список резюме подтянется)")
        return
    if not by_resume and not query:
        db.log("Укажите поисковый запрос для hh")
        return
    resume_title = next((r["title"] for r in json.loads(s["hh_resumes"] or "[]") if r["hash"] == s["hh_resume_hash"]), "")
    source = f"найдена среди подходящих к резюме «{resume_title}»" if by_resume else f"найдена по запросу «{query}»"
    if fresh:
        source += ", опубликована за последние сутки"
    experience = [c for c in (s["f_experience"] or "").split(",") if c in EXPERIENCE_CODES]
    rejected = filters.rejected_companies() if s["f_skip_rejected"] == "1" else set()
    pages = db.num(s, "hh_pages")
    added = passed = with_match = 0
    with sync_playwright() as p:
        ctx, page = _open(p)
        for n in range(pages):
            if job.stop_requested:
                break
            if by_resume:  # the same list hh shows as «подходящие вакансии» for the resume
                url = f"https://{domain}/search/vacancy?resume={s['hh_resume_hash']}&page={n}&items_on_page=50"
            else:
                url = f"https://{domain}/search/vacancy?text={quote(query)}&page={n}&items_on_page=50"
            if s["hh_area"].strip():
                url += f"&area={s['hh_area'].strip()}"
            url += "".join(f"&experience={c}" for c in experience)
            if s["f_skip_no_salary"] == "1":
                url += "&only_with_salary=true"
            if fresh:
                url += "&order_by=publication_time&search_period=1"
            page.goto(url, wait_until="domcontentloaded")
            if not _wait_captcha(page):
                break
            # results are rendered by JS: wait for cards instead of a fixed pause
            if not _visible(page, 'a[data-qa="serp-item__title"]', timeout=15000):
                _wait_captcha(page)
                if not _visible(page, 'a[data-qa="serp-item__title"]', timeout=5000):
                    if n > 0:  # simply ran out of result pages
                        break
                    shot = SCREENS_DIR / f"search_page{n + 1}.png"
                    page.screenshot(path=str(shot))
                    db.log(f"hh: на странице {n + 1} нет вакансий (скриншот: data/screens/{shot.name})")
                    break
            page.wait_for_timeout(800)
            items = page.evaluate(SERP_JS)
            if not items:
                db.log(f"hh: страница {n + 1} пустая, поиск завершён")
                break
            for it in items:
                m = re.search(r"/vacancy/(\d+)", it["href"])
                if not m:
                    continue
                vid = m.group(1)
                lo, hi = filters.parse_salary(it["salary"])
                v = {
                    "title": it["title"].replace("\n", " "), "company": it["company"].replace("\n", " "),
                    "salary_text": it["salary"] or None, "salary_from": lo, "salary_to": hi,
                    "experience": it["experience"] or None, "skill_match": it["match"],
                }
                with_match += it["match"] is not None
                ok, note, reasons = filters.check(v, s, rejected, source)
                url_v = f"https://{domain}/vacancy/{vid}"
                if not db.x(
                    "INSERT OR IGNORE INTO vacancies(source, ext_id, url, title, company, status, note, created_at, salary_text, "
                    "salary_from, salary_to, experience, skill_match, match_info) VALUES ('hh', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (vid, url_v, v["title"], v["company"], "new" if ok else "skipped", note, db.now(), v["salary_text"],
                     lo, hi, v["experience"], v["skill_match"], json.dumps(reasons, ensure_ascii=False)),
                ):
                    continue
                added += 1
                passed += ok
                row_id = db.q("SELECT id FROM vacancies WHERE url=?", (url_v,))[0]["id"]
                db.event(row_id, "found", source[0].upper() + source[1:])
                if not ok:
                    db.event(row_id, "filtered", f"Отсеяна фильтром: {note}")
            db.log(f"hh: страница {n + 1} — найдено {len(items)} вакансий")
            page.wait_for_timeout(random.randint(1500, 3500))
        ctx.close()
    if added and not with_match:
        db.log("hh: на этих страницах hh не показал «совпадение навыков», сортировка по нему недоступна")
    db.log(f"hh: поиск завершён, новых вакансий: {added}, прошли фильтры: {passed}")
    return passed


def _pick_resume(page, resume_hash, resume_title) -> bool:
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


def _fill_questionnaire(page, given=None) -> list[str]:
    """Fill employer questions from the answer base. Returns questions that have no answer; appends {q, a} to given."""
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
        if done and given is not None:
            given.append({"q": question, "a": ans})
        if not done:
            missing.append(question)
            answers.remember_unknown(question, "form")
    return missing


LETTER_TOGGLE = '[data-qa="vacancy-response-letter-toggle"]'
LETTER_BOX = '[data-qa="vacancy-response-popup-form-letter-input"]'
LETTER_SEND = '[data-qa="vacancy-response-letter-submit"]'


def _attach_letter_after_response(page, letter) -> bool:
    """hh often sends the response in one click; the letter is then added via «Приложить сопроводительное письмо»."""
    if not _visible(page, LETTER_BOX, timeout=500):
        if not _visible(page, LETTER_TOGGLE, timeout=5000):
            return False
        page.locator(LETTER_TOGGLE).first.click()
    if not _visible(page, LETTER_BOX, timeout=3000):
        return False
    page.locator(LETTER_BOX).first.fill(letter)
    if not _visible(page, LETTER_SEND, timeout=2000):
        return False
    page.locator(LETTER_SEND).first.click()
    page.wait_for_timeout(2500)
    return not _visible(page, LETTER_BOX)  # the form disappears once the letter is sent


def _find_chat_id(page, domain, title, company):
    """The «Чат» control on a vacancy page has no link, so find the chat by vacancy title in the chat list."""
    page.goto(f"https://{domain}/chat", wait_until="domcontentloaded")
    try:
        page.locator('[data-qa^="chatik-open-chat-"]').first.wait_for(timeout=15000)
    except PWTimeout:
        return None
    return page.evaluate(
        """([title, company]) => {
            const norm = s => (s || '').toLowerCase().replace(/[«»"]/g, '').replace(/\\s+/g, ' ').trim();
            const words = norm(company).split(' ').filter(w => w.length > 3 && !['филиал', 'акционерного', 'общества'].includes(w));
            const cells = [...document.querySelectorAll('[data-qa^="chatik-open-chat-"]')]
                .filter(e => norm(e.innerText.split('\\n')[0]) === norm(title));
            const hit = cells.find(e => words.some(w => norm(e.innerText).includes(w))) || cells[0];
            return hit ? hit.dataset.qa.replace('chatik-open-chat-', '') : null;
        }""",
        [title, company or ""],
    )


def _letter_via_chat(page, domain, letter, title, company) -> bool:
    """Send the letter as a message in the vacancy chat."""
    import chat_bot  # local import: chat_bot imports this module
    cid = _find_chat_id(page, domain, title, company)
    if not cid:
        return False
    page.goto(f"https://{domain}/chat/{cid}", wait_until="domcontentloaded")
    return chat_bot._read_chat(page) is not None and chat_bot._send(page, letter)


def _apply_one(page, domain, v, letter, resume_hash=None, resume_title=None) -> tuple[str, str, dict]:
    """Returns (status, note, info) where info = {"letter": bool, "letter_via": "form"/"chat", "resume": title or None
    if hh chose it, "form": [{q, a}]}."""
    info = {"letter": False, "letter_via": None, "resume": None, "form": []}
    page.goto(f"https://{domain}/vacancy/{v['ext_id']}", wait_until="domcontentloaded")
    if not _wait_captcha(page):
        return "error", "капча", info
    page.wait_for_timeout(1200)

    if _visible(page, SUCCESS_MARKERS[0]):
        return "applied", "отклик уже был", info

    btn = '[data-qa="vacancy-response-link-top"]'
    if not _visible(page, btn, timeout=5000):
        return "skipped", "нет кнопки отклика (архив или внешний сайт)", info
    page.locator(btn).first.click()
    page.wait_for_timeout(2000)

    if _visible(page, '[data-qa="relocation-warning-confirm"]'):
        page.locator('[data-qa="relocation-warning-confirm"]').first.click()
        page.wait_for_timeout(1500)

    submit = '[data-qa="vacancy-response-submit-popup"]'
    if "vacancy_response" in page.url or _visible(page, submit, timeout=1500):
        # a form before sending: questionnaire and/or resume choice; the letter goes with the response
        if resume_hash and _pick_resume(page, resume_hash, resume_title):
            info["resume"] = resume_title
        missing = _fill_questionnaire(page, info["form"])
        if missing:
            return "attention", "анкета, нет ответа на: " + "; ".join(q[:80] for q in missing), info
        if letter:
            if not _visible(page, LETTER_BOX, timeout=500) and _visible(page, LETTER_TOGGLE):
                page.locator(LETTER_TOGGLE).first.click()
            if _visible(page, LETTER_BOX, timeout=2000):
                page.locator(LETTER_BOX).first.fill(letter)
                info["letter"], info["letter_via"] = True, "form"
        if _visible(page, submit):
            page.locator(submit).first.click()
            page.wait_for_timeout(2500)

    if not any(_visible(page, m, timeout=3000 if i == 0 else 0) for i, m in enumerate(SUCCESS_MARKERS)):
        shot = SCREENS_DIR / f"hh_{v['ext_id']}.png"
        page.screenshot(path=str(shot))
        return "error", f"не удалось подтвердить отклик, скриншот: data/screens/{shot.name}", info

    # one-click response: attach the letter right after it, or send it to the chat
    if letter and not info["letter"]:
        info["letter"] = _attach_letter_after_response(page, letter)
        info["letter_via"] = "form" if info["letter"] else None
        if not info["letter"]:
            try:
                info["letter"] = _letter_via_chat(page, domain, letter, v["title"], v["company"])
            except Exception:
                info["letter"] = False
            info["letter_via"] = "chat" if info["letter"] else None
    return "applied", None if info["letter"] or not letter else "отклик ушёл, но письмо приложить не удалось", info


def apply_queue():
    import filters

    s = db.get_settings()
    domain = s["hh_domain"]
    limit = db.num(s, "hh_daily_limit")
    pause_lo = db.num(s, "hh_pause_min", 0)
    pause_hi = max(pause_lo, db.num(s, "hh_pause_max", 0))
    order = "skill_match IS NULL, skill_match DESC, id" if s["f_sort_match"] == "1" else "id"
    queue = db.q(f"SELECT * FROM vacancies WHERE source='hh' AND status='queued' ORDER BY {order}")
    resume_hash = s["hh_resume_hash"]
    resume_title = next((r["title"] for r in json.loads(s["hh_resumes"] or "[]") if r["hash"] == resume_hash), None)
    rejected = filters.rejected_companies() if s["f_skip_rejected"] == "1" else set()
    if not queue:
        db.log("hh: очередь пуста — отметьте вакансии и нажмите «В очередь»")
        return
    db.log(f"hh: отклики пойдут с резюме «{resume_title or 'первое в списке hh'}»")
    with sync_playwright() as p:
        ctx, page = _open(p)
        if not is_logged_in(page, domain):
            db.log("hh: вы не вошли в аккаунт — нажмите «Войти в hh»")
            ctx.close()
            return
        for v in queue:
            if job.stop_requested:
                db.log("Остановлено пользователем")
                break
            done_today = db.count_today("vacancies", "applied_at", "applied", "AND source='hh'")
            if done_today >= limit:
                db.log(f"hh: достигнут дневной лимит ({limit}). Остальное завтра")
                break
            if v["company"] and filters.norm(v["company"]) in rejected:  # the refusal may have come after it was queued
                note = "эта компания уже отказала вам раньше"
                db.x("UPDATE vacancies SET status='skipped', note=? WHERE id=?", (note, v["id"]))
                db.event(v["id"], "filtered", f"Не откликаюсь: {note}")
                continue
            letter = db.fill(s["hh_letter_template"], company=v["company"], position=v["title"])
            info = {"letter": False, "letter_via": None, "resume": None, "form": []}
            try:
                status, note, info = _apply_one(page, domain, v, letter, resume_hash, resume_title)
            except Exception as e:  # keep going on single failures
                status, note = "error", str(e)[:300]
            applied = status == "applied" and note != "отклик уже был"
            db.x(
                "UPDATE vacancies SET status=?, note=?, applied_at=?, resume=?, letter_sent=?, letter=?, "
                "form_answers=COALESCE(?, form_answers) WHERE id=?",
                (status, note, db.now() if applied else None,
                 (info["resume"] or "по умолчанию на hh") if applied else None,
                 int(info["letter"]) if applied else None, letter if applied and info["letter"] else None,
                 json.dumps(info["form"], ensure_ascii=False) if info["form"] else None, v["id"]),
            )
            if applied:
                db.event(v["id"], "applied", f"Отклик отправлен с резюме «{info['resume'] or 'по умолчанию на hh'}»")
                if info["form"]:
                    db.event(v["id"], "form", f"Анкета заполнена из базы ответов: {len(info['form'])} вопр.")
                if info["letter"]:
                    db.event(v["id"], "letter", "Письмо приложено к отклику" if info["letter_via"] == "form" else "Письмо отправлено в чат вакансии")
                elif letter:
                    db.event(v["id"], "error", "Письмо приложить не удалось")
            elif note == "отклик уже был":
                db.event(v["id"], "applied", "Отклик уже был сделан раньше")
            else:
                db.event(v["id"], "attention" if status == "attention" else "error" if status == "error" else "skipped",
                         {"attention": "Нужны ваши ответы на анкету", "skipped": "Пропущена"}.get(status, "Ошибка") + (f": {note}" if note else ""))
            human = {"applied": "отклик отправлен", "skipped": "пропущена", "attention": "нужны ответы на анкету", "error": "ошибка"}
            extra = (" + письмо ✓" if info["letter"] else "") if applied else ""
            db.log(f"hh: {v['title']} — {v['company']}: {human.get(status, status)}{extra}{' (' + note + ')' if note else ''}")
            page.wait_for_timeout(random.randint(pause_lo, pause_hi) * 1000)
        ctx.close()
    db.log("hh: обработка очереди завершена")


STATE_NAMES = {
    "not-viewed": "не просмотрен", "viewed": "просмотрен", "discard": "отказ",
    "invitation": "приглашение", "invite": "приглашение", "interview": "собеседование",
    "hired": "выход на работу", "archived": "в архиве",
}


def sync_responses():
    """Read hh «Отклики» and store the employer's reaction for every response (incl. ones made by hand)."""
    s = db.get_settings()
    domain = s["hh_domain"]
    seen = updated = added = 0
    with sync_playwright() as p:
        ctx, page = _open(p)
        if not is_logged_in(page, domain):
            db.log("hh: вы не вошли в аккаунт — нажмите «Войти в hh»")
            ctx.close()
            return
        prev_first = None
        for n in range(50):
            if job.stop_requested:
                break
            page.goto(f"https://{domain}/applicant/negotiations?filter=all&page={n}", wait_until="domcontentloaded")
            if not _wait_captcha(page) or not _visible(page, '[data-qa="negotiations-item"]', timeout=10000):
                break
            items = page.evaluate(
                """() => [...document.querySelectorAll('[data-qa="negotiations-item"]')].map(it => {
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
            )
            if not items or items[0]["href"] == prev_first:
                break
            prev_first = items[0]["href"]
            for it in items:
                m = re.search(r"/vacancy/(\d+)", it["href"])
                if not m:
                    continue
                vid, seen = m.group(1), seen + 1
                state = STATE_NAMES.get(it["state"]) or it["state_text"].lower() or it["state"]
                row = db.q("SELECT id, hh_state FROM vacancies WHERE source='hh' AND ext_id=?", (vid,))
                if row:
                    updated += db.x(
                        "UPDATE vacancies SET status='applied', hh_state=?, hh_state_at=?, "
                        "invited_at=CASE WHEN invited_at IS NULL AND ? THEN ? ELSE invited_at END WHERE id=?",
                        (state, db.now(), state in db.INVITE_STATES, db.now(), row[0]["id"]),
                    )
                    if state != row[0]["hh_state"]:
                        db.event(row[0]["id"], "employer", f"Работодатель: {state}")
                    pipeline.ensure_stages()
                    pipeline.advance_from_hh(row[0]["id"], state)
                else:
                    added += db.x(
                        "INSERT OR IGNORE INTO vacancies(source, ext_id, url, title, company, status, note, "
                        "hh_state, hh_state_at, created_at) VALUES ('hh', ?, ?, ?, ?, 'applied', ?, ?, ?, ?)",
                        # applied_at stays empty: the real date is only known as text, and it must not eat today's limit
                        (vid, f"https://{domain}/vacancy/{vid}", it["title"], it["company"],
                         f"отклик сделан вне бота ({it['date']})", state, db.now(), db.now()),
                    )
                    new_id = db.q("SELECT id FROM vacancies WHERE source='hh' AND ext_id=?", (vid,))
                    if new_id:
                        if state in db.INVITE_STATES:
                            db.x("UPDATE vacancies SET invited_at=? WHERE id=?", (db.now(), new_id[0]["id"]))
                        db.event(new_id[0]["id"], "applied", f"Отклик сделан вне бота ({it['date']})")
                        db.event(new_id[0]["id"], "employer", f"Работодатель: {state}")
                        pipeline.ensure_stages()
            page.wait_for_timeout(random.randint(1200, 2500))
        ctx.close()
    db.log(f"hh: синхронизация откликов — всего {seen}, обновлено {updated}, добавлено {added}")


def send_missing_letters():
    """Send the cover letter to the chat for responses that went out without it."""
    s = db.get_settings()
    domain = s["hh_domain"]
    rows = db.q("SELECT * FROM vacancies WHERE source='hh' AND status='applied' AND letter_sent=0 ORDER BY id")
    if not rows:
        db.log("hh: все отклики уже с письмами")
        return
    import chat_bot
    with sync_playwright() as p:
        ctx, page = _open(p)
        if not is_logged_in(page, domain):
            db.log("hh: вы не вошли в аккаунт — нажмите «Войти в hh»")
            ctx.close()
            return
        for v in rows:
            if job.stop_requested:
                break
            letter = db.fill(s["hh_letter_template"], company=v["company"], position=v["title"])
            ok = False
            try:
                ok = _letter_via_chat(page, domain, letter, v["title"], v["company"])
            except Exception as e:
                db.log(f"hh: {v['title']}: ошибка {e}")
            if ok:
                db.x("UPDATE vacancies SET letter_sent=1, letter=? WHERE id=?", (letter, v["id"]))
                db.event(v["id"], "letter", "Письмо дослано в чат вакансии")
            db.log(f"hh: письмо к «{v['title']}» — {v['company']}: {'отправлено в чат ✓' if ok else 'не удалось отправить'}")
            page.wait_for_timeout(random.randint(3000, 6000))
        ctx.close()


def send_followups():
    """Send the follow-ups you approved («напомнить о себе») to the vacancy chats."""
    s = db.get_settings()
    domain = s["hh_domain"]
    rows = db.q("SELECT * FROM vacancies WHERE followup='approved' ORDER BY id")
    if not rows:
        return
    with sync_playwright() as p:
        ctx, page = _open(p)
        if not is_logged_in(page, domain):
            db.log("hh: вы не вошли в аккаунт — нажмите «Войти в hh»")
            ctx.close()
            return
        for v in rows:
            if job.stop_requested:
                break
            ok = False
            try:
                ok = _letter_via_chat(page, domain, v["followup_text"], v["title"], v["company"])
            except Exception as e:
                db.log(f"hh: {v['title']}: ошибка {e}")
            if ok:
                db.x("UPDATE vacancies SET followup='sent', followup_at=? WHERE id=?", (db.now(), v["id"]))
                db.event(v["id"], "followup", "Вы напомнили о себе в чате")
            db.log(f"hh: напоминание о себе — {v['company']}: {'отправлено ✓' if ok else 'не удалось, попробую позже'}")
            page.wait_for_timeout(random.randint(3000, 6000))
        ctx.close()
