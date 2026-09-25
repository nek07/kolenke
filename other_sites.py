"""Monitoring of other job sites (Хабр Карьера, Enbek): find vacancies, read salary, place and contacts.
Read-only: no login, no «Откликнуться». Contacts can later go to «Письма компаниям»."""
import html
import json
import random
import re
from urllib.parse import quote

from playwright.sync_api import sync_playwright

import db
import filters
from jobs import job

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")  # Enbek blocks the default headless user agent
SITE_NAMES = {"habr": "Хабр Карьера", "enbek": "Enbek"}

# ---------- contacts ----------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
TG_RE = re.compile(r"(?:t\.me/|telegram\.me/)([A-Za-z0-9_]{4,32})|(?:telegram|телеграм|tg)\W{0,3}@([A-Za-z0-9_]{4,32})", re.I)
JUNK_EMAIL = re.compile(r"noreply|no-reply|example\.|sentry|@2x|\.(png|jpe?g|svg|gif|webp)$|support@habr|@habr\.|@enbek\.kz$", re.I)


def extract_contacts(text: str) -> dict:
    """E-mails, phones and Telegram handles mentioned in free text."""
    text = text or ""
    emails = []
    for e in EMAIL_RE.findall(text):
        e = e.strip(".").lower()
        if not JUNK_EMAIL.search(e) and e not in emails:
            emails.append(e)
    phones = []
    for ph in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", ph)
        digits = "7" + digits[1:] if digits.startswith("8") else digits
        if len(digits) == 11:
            nice = f"+7 {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:]}"
            if nice not in phones:
                phones.append(nice)
    tg = []
    for a, b in TG_RE.findall(text):
        h = "@" + (a or b)
        if h.lower() not in [t.lower() for t in tg]:
            tg.append(h)
    return {"emails": emails, "phones": phones, "telegram": tg}


def merge_contacts(*parts) -> dict:
    out = {"emails": [], "phones": [], "telegram": [], "person": ""}
    for p in parts:
        for k in ("emails", "phones", "telegram"):
            for x in p.get(k) or []:
                if x not in out[k]:
                    out[k].append(x)
        out["person"] = out["person"] or p.get("person") or ""
    return out


# ---------- place ----------
KZ_CITIES = ("алматы", "астана", "нур-султан", "шымкент", "караганд", "актобе", "атырау", "актау", "павлодар", "усть-каменогорск",
             "семей", "костанай", "кызылорд", "тараз", "уральск", "петропавловск", "туркестан", "талдыкорган", "кокшетау", "экибастуз")
COUNTRY_BY_CITY = {
    "Россия": ("москва", "санкт-петербург", "новосибирск", "екатеринбург", "казань", "нижний новгород", "самара", "краснодар",
               "ростов", "пермь", "воронеж", "уфа", "челябинск", "омск", "томск", "иннополис", "калининград", "тюмень", "россия"),
    "Беларусь": ("минск", "беларусь"),
    "Узбекистан": ("ташкент", "узбекистан"),
    "Кыргызстан": ("бишкек", "кыргызстан"),
    "Армения": ("ереван",), "Грузия": ("тбилиси",), "Сербия": ("белград",), "Кипр": ("лимасол", "кипр"),
}


def country_of(locations, remote=False) -> str:
    low = " ".join(locations or []).lower()
    if any(c in low for c in KZ_CITIES) or "казахстан" in low:
        return "Казахстан"
    for country, cities in COUNTRY_BY_CITY.items():
        if any(c in low for c in cities):
            return country
    return "Удалённо" if remote else ""


def currency_of(salary_text) -> str:
    t = (salary_text or "").lower()
    if "₽" in t or "руб" in t:
        return "RUB"
    if "$" in t or "usd" in t:
        return "USD"
    if "€" in t or "eur" in t:
        return "EUR"
    return "KZT" if ("₸" in t or "тенге" in t or "kzt" in t or re.search(r"\d", t)) else ""


# ---------- page readers (run inside the browser; also used by the fixture tests) ----------
HABR_LIST_JS = """() => [...document.querySelectorAll('.vacancy-card')].map(c => {
    const a = c.querySelector('.vacancy-card__title-link');
    const comp = c.querySelector('.vacancy-card__company a');
    const chips = [...new Set([...c.querySelectorAll('.vacancy-card__meta .basic-chip, .vacancy-card__meta a, .vacancy-card__meta .chip-with-icon__text')]
        .map(e => e.innerText.trim()).filter(Boolean))];
    const salary = c.querySelector('.vacancy-card__salary .basic-salary');   // «Похожие специалисты получают» is a forecast, not a salary
    const time = c.querySelector('.vacancy-card__date time');
    return a && {
        href: a.getAttribute('href'), title: a.innerText.trim(),
        company: comp ? comp.innerText.trim() : '', company_href: comp ? comp.getAttribute('href') : '',
        salary: salary ? salary.innerText.trim() : '', chips,
        skills: [...c.querySelectorAll('.vacancy-card__skills .basic-chip')].map(e => e.innerText.trim()),
        published: time ? time.getAttribute('datetime') : '',
    };
}).filter(Boolean)"""

HABR_DETAIL_JS = """() => {
    const d = document.querySelector('.vacancy-description__text');
    const comp = document.querySelector('.company_name a, a[href^="/companies/"]');
    return {text: d ? d.innerText : '', company_href: comp ? comp.getAttribute('href') : ''};
}"""

ENBEK_LIST_JS = """() => [...document.querySelectorAll('.item-list')].map(c => {
    const a = c.querySelector('a.stretched');
    const t = sel => { const e = c.querySelector(sel); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : ''; };
    return a && {
        href: a.getAttribute('href'), title: (a.innerText || a.getAttribute('title') || '').replace(/\\s+/g, ' ').trim(), subtitle: t('.subtitle'),
        company: t('.company-name') || t('.company'), location: t('li.location'), experience: t('li.experience'),
        schedule: t('li.time'), salary: t('.price'),
    };
}).filter(Boolean)"""

ENBEK_DETAIL_JS = """() => {
    const body = document.body.innerText;
    const between = (a, b) => { const i = body.indexOf(a); if (i < 0) return ''; const j = body.indexOf(b, i + a.length); return body.slice(i + a.length, j > 0 ? j : i + 600).trim(); };
    const tel = document.querySelector('a[href^="tel:"]');
    let person = '';
    if (tel) {   // the contact person is the line right above the phone
        let box = tel; for (let i = 0; i < 4 && box.parentElement; i++) box = box.parentElement;
        const lines = box.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
        const k = lines.findIndex(l => l.replace(/\\D/g, '').length >= 10);
        if (k > 0 && !/работник|област|район|ул\\.|көшесі|\\d{3}/i.test(lines[k - 1])) person = lines[k - 1];
    }
    const price = document.querySelector('.price');
    return {
        salary: price ? price.innerText.trim() : '',
        duties: between('Обязанности', 'Личные качества') || between('Обязанности', 'Регион'),
        emails: [...document.querySelectorAll('a[href^="mailto:"]')].map(a => a.getAttribute('href').slice(7).split('?')[0]),
        phones_raw: [...document.querySelectorAll('a[href^="tel:"]')].map(a => a.getAttribute('href').slice(4)).join(' '),
        person,
    };
}"""


# ---------- normalizers (pure Python, unit-tested) ----------
LEVELS = ("Intern", "Junior", "Middle", "Senior", "Lead")


def normalize_habr(raw: dict) -> dict:
    chips = raw.get("chips") or []
    remote = any("удал" in c.lower() for c in chips)
    level = next((c for c in chips if c in LEVELS), "")
    places = [c for c in chips if c not in LEVELS and "удал" not in c.lower() and "полный" not in c.lower()]
    m = re.search(r"/vacancies/(\d+)", raw.get("href") or "")
    return {
        "source": "habr", "ext_id": m.group(1) if m else None, "url": "https://career.habr.com" + (raw.get("href") or ""),
        "title": raw.get("title", ""), "company": raw.get("company", ""),
        "company_url": ("https://career.habr.com" + raw["company_href"]) if raw.get("company_href") else "",
        "salary_text": raw.get("salary") or None, "experience": level or None, "remote": int(remote),
        "location": ", ".join(places), "country": country_of(places, remote),
        "skills": ", ".join(raw.get("skills") or []),
    }


def normalize_enbek(raw: dict) -> dict:
    m = re.search(r"~(\d+)", raw.get("href") or "")
    loc = raw.get("location", "")
    # the link holds the profession from the state classifier, the subtitle holds the employer's own job title
    own, profession = (raw.get("subtitle") or "").strip(), (raw.get("title") or "").strip()
    return {
        "source": "enbek", "ext_id": m.group(1) if m else None,
        "url": raw["href"] if raw.get("href", "").startswith("http") else "https://www.enbek.kz" + (raw.get("href") or ""),
        "title": own or profession, "company": raw.get("company", ""), "company_url": "",
        "salary_text": raw.get("salary") or None, "experience": raw.get("experience") or None, "remote": 0,
        "location": loc, "country": "Казахстан", "skills": f"профессия: {profession}" if own and profession != own else "",
        "schedule": raw.get("schedule", ""),
    }


def tidy_salary(text):
    """Enbek writes a fixed salary as «от 800 000 до 800 000 тенге»."""
    if not text:
        return text
    t = re.sub(r"\s+", " ", text).strip()
    m = re.fullmatch(r"от ([\d ]*\d) до ([\d ]*\d) (\D.*)", t)
    return f"{m.group(1)} {m.group(3)}" if m and m.group(1) == m.group(2) else t


def summarize(text, limit=280) -> str:
    t = re.sub(r"\s+", " ", html.unescape(text or "")).strip()  # Enbek keeps entities like &middot; in its texts
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def evaluate(v: dict, s: dict, rejected: set):
    """Filters shared with hh + the country filter. Salary floors are in tenge: other currencies are not compared."""
    v["salary_from"], v["salary_to"] = filters.parse_salary(v.get("salary_text"))
    cur = currency_of(v.get("salary_text"))
    s2 = dict(s)
    extra = []
    if v.get("salary_text") and cur and cur != "KZT" and s.get("f_salary_min"):
        s2["f_salary_min"] = ""
        extra.append({"ok": True, "text": f"зарплата в {cur}: фильтр «не ниже» в тенге не применялся"})
    site = SITE_NAMES.get(v["source"], v["source"])
    ok, note, reasons = filters.check(v, s2, rejected, f"найдена на {site} по запросу «{s.get('other_query') or ''}»")
    reasons += extra
    wanted = filters.split_list(s.get("other_countries"))  # countries and/or cities: «Казахстан», «астана», «удалённо»
    if wanted:
        where = filters.norm(f"{v.get('country') or ''} {v.get('location') or ''}")
        good = any(w in where for w in wanted if "удал" not in w) or (v.get("remote") and any("удал" in w for w in wanted))
        place = ", ".join(x for x in (v.get("location"), v.get("country")) if x) or "место не указано"
        text = f"место: {place}" + (" (можно удалённо)" if v.get("remote") else "")
        reasons.append({"ok": bool(good), "text": text})
        if not good and ok:
            ok, note = False, f"{text} — не из вашего списка мест"
    return ok, note, reasons


# ---------- crawling ----------
def _goto(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)


def _habr(page, query, pages):
    found = []
    for n in range(1, pages + 1):
        _goto(page, f"https://career.habr.com/vacancies?q={quote(query)}&type=all&page={n}")
        items = page.evaluate(HABR_LIST_JS)
        if not items:
            break
        found += [normalize_habr(r) for r in items]
    return found


def _habr_details(page, v, company_cache):
    _goto(page, v["url"])
    try:  # the description is rendered a moment after the page
        page.wait_for_function("() => (document.querySelector('.vacancy-description__text')?.innerText || '').trim().length > 0", timeout=4000)
    except Exception:
        pass
    d = page.evaluate(HABR_DETAIL_JS)
    v["summary"] = summarize(d["text"]) or (f"Навыки: {v['skills']}" if v.get("skills") else "Работодатель не заполнил описание")
    contacts = [extract_contacts(d["text"])]
    curl = v.get("company_url") or (("https://career.habr.com" + d["company_href"]) if d.get("company_href") else "")
    if curl:
        v["company_url"] = curl
        if curl not in company_cache:  # HR e-mails usually live on the company page
            try:
                _goto(page, curl)
                company_cache[curl] = extract_contacts(page.evaluate("document.body.innerText"))
            except Exception:
                company_cache[curl] = {}
        contacts.append(company_cache[curl])
    v["contacts"] = merge_contacts(*contacts)


def _enbek(page, query, pages):
    found = []
    for n in range(1, pages + 1):
        _goto(page, f"https://www.enbek.kz/ru/search/vacancy?prof={quote(query)}&page={n}")
        page.wait_for_timeout(1500)
        items = page.evaluate(ENBEK_LIST_JS)
        new = [normalize_enbek(r) for r in items]
        if not new or (found and new[0]["url"] == found[0]["url"]):  # past the last page the site repeats page 1
            break
        found += new
    return found


def _enbek_details(page, v):
    _goto(page, v["url"])
    d = page.evaluate(ENBEK_DETAIL_JS)
    v["salary_text"] = tidy_salary(d["salary"] or v.get("salary_text"))
    v["summary"] = summarize(d["duties"])
    phones = extract_contacts(d["phones_raw"])["phones"]
    v["contacts"] = merge_contacts({"emails": [e.lower() for e in d["emails"]], "phones": phones, "person": d["person"]},
                                   extract_contacts(d["duties"]))


def monitor():
    """Search the chosen sites, open new vacancies once, store them with contacts. Returns how many passed the filters."""
    s = db.get_settings()
    query = (s["other_query"] or s["hh_query"] or s["desired_position"]).strip()  # a search phrase beats a job title
    sites = [x for x in filters.split_list(s["other_sites"]) if x in SITE_NAMES]
    if not query or not sites:
        db.log("Другие сайты: укажите запрос и хотя бы один сайт")
        return 0
    s["other_query"] = query
    pages = db.num(s, "other_pages")
    max_details = db.num(s, "other_max_details", 0)  # new vacancy pages opened per run (0 = only the lists)
    rejected = filters.rejected_companies() if s["f_skip_rejected"] == "1" else set()
    known = {r["url"] for r in db.q("SELECT url FROM vacancies WHERE source IN ('habr','enbek')")}
    added = passed = details = 0
    company_cache = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(locale="ru-RU", user_agent=UA).new_page()
        for site in sites:
            if job.stop_requested:
                break
            try:
                items = _habr(page, query, pages) if site == "habr" else _enbek(page, query, pages)
            except Exception as e:
                db.log(f"{SITE_NAMES[site]}: не удалось открыть поиск ({str(e)[:80]})")
                continue
            fresh = [v for v in items if v["ext_id"] and v["url"] not in known]
            db.log(f"{SITE_NAMES[site]}: найдено {len(items)}, новых {len(fresh)}")
            for v in fresh:
                if job.stop_requested:
                    break
                v["contacts"], v["summary"] = merge_contacts(), ""
                if details < max_details:
                    try:
                        _habr_details(page, v, company_cache) if site == "habr" else _enbek_details(page, v)
                        details += 1
                        page.wait_for_timeout(random.randint(800, 2000))
                    except Exception as e:  # one broken page must not stop the run
                        v["summary"] = f"Страницу вакансии открыть не удалось: {str(e)[:60]}"
                ok, note, reasons = evaluate(v, s, rejected)
                if save(v, ok, note, reasons):
                    added += 1
                    passed += ok
                    known.add(v["url"])
        browser.close()
    left = " (остальные откроются в следующий раз)" if max_details and details >= max_details else ""
    db.log(f"Другие сайты: новых вакансий {added}, прошли фильтры {passed}{left}")
    return passed


def save(v, ok, note, reasons) -> bool:
    if not db.x(
        "INSERT OR IGNORE INTO vacancies(source, ext_id, url, title, company, status, note, created_at, salary_text, salary_from, "
        "salary_to, experience, match_info, location, country, remote, summary, contacts, company_url, skills) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (v["source"], v["ext_id"], v["url"], v["title"], v["company"], "new" if ok else "skipped", note, db.now(),
         v.get("salary_text"), v.get("salary_from"), v.get("salary_to"), v.get("experience"),
         json.dumps(reasons, ensure_ascii=False), v.get("location"), v.get("country"), v.get("remote", 0), v.get("summary"),
         json.dumps(v.get("contacts") or {}, ensure_ascii=False), v.get("company_url"), v.get("skills")),
    ):
        return False
    vid = db.q("SELECT id FROM vacancies WHERE url=?", (v["url"],))[0]["id"]
    db.event(vid, "found", f"Найдена на {SITE_NAMES.get(v['source'], v['source'])}")
    if not ok:
        db.event(vid, "filtered", f"Отсеяна фильтром: {note}")
    return True


def to_companies(ids) -> dict:
    """Put the e-mails of chosen vacancies into «Письма компаниям» (position = vacancy title)."""
    added = no_email = 0
    for i in ids:
        rows = db.q("SELECT id, company, title, contacts FROM vacancies WHERE id=?", (i,))
        if not rows:
            continue
        v = rows[0]
        emails = (json.loads(v["contacts"] or "{}")).get("emails") or []
        if not emails:
            no_email += 1
            continue
        n = sum(db.x("INSERT OR IGNORE INTO companies(name, email, position, created_at) VALUES (?, ?, ?, ?)",
                     (v["company"], e, v["title"], db.now())) for e in emails)
        added += n
        if n:
            db.event(v["id"], "contact", f"Почта добавлена в «Письма компаниям»: {', '.join(emails)}")
    return {"added": added, "no_email": no_email}
