"""The market for a role and grade: real vacancies, the skills they ask for, how often, and the salary range.

hh's public API no longer answers without an employer or app token, but the public pages do, so a small sample is read
the way a browser would: one search page, then up to N vacancy pages with a pause between them. No login is used and
the bot's browser is not involved, so a review can run while the autopilot works. Samples are kept for a day.
Vacancies the bot already found on other sites (Хабр, Enbek) with their skills are added to the sample."""
import html
import json
import random
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from statistics import quantiles
from urllib.parse import quote

from kolenke.db.connection import now, query, transaction
from kolenke.schemas.enums import Grade
from kolenke.schemas.resume import Market, MarketSkill, MarketVacancyRef, Salary
from kolenke.services.filters import parse_salary
from kolenke.services.resume import skills
from kolenke.services.resume.profiles import GRADES
from kolenke.services.text import currency_of, norm

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
CACHE_HOURS = 24
TITLE_STOP = {"в", "на", "и", "с", "по", "для", "the", "of", "senior", "middle", "junior", "lead", "ведущий", "старший",
              "младший", "главный", "стажер", "стажёр", "intern", "специалист", "г", "удаленно", "удалённо", "remote"}

Progress = Callable[[str], None]


class Blocked(Exception):
    """hh answered with a captcha or refused: stop reading and use what was collected."""


# ---------- fetching ----------
def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9", "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if "captcha" in r.geturl():
                raise Blocked()
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise Blocked() from e
        raise


# without a region hh.kz searches every hh country, and the sample becomes mostly Russian vacancies
DEFAULT_AREA = {"hh.kz": "40", "hh.uz": "97", "rabota.by": "16"}


def search_url(domain: str, query_text: str, grade: Grade, area: str, page: int = 0) -> str:
    url = f"https://{domain}/search/vacancy?text={quote(query_text)}&items_on_page=50&page={page}&order_by=relevance"
    url += "".join(f"&experience={e.value}" for e in GRADES[grade].hh_experience)
    area = area or DEFAULT_AREA.get(domain, "")
    if area:
        url += f"&area={area}"
    return url


_TITLE_LINK = re.compile(r'<a\b[^>]*data-qa="serp-item__title"[^>]*>')
_HREF_ID = re.compile(r'href="[^"]*/vacancy/(\d+)')


def parse_search(page_html: str) -> list[str]:
    """Vacancy ids of a search page, in order, without duplicates (promoted cards repeat)."""
    ids = []
    for tag in _TITLE_LINK.findall(page_html):
        m = _HREF_ID.search(tag)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_vacancy(page_html: str, url: str) -> dict | None:
    """Title, company, key skills, experience, salary and description of an hh vacancy page."""
    posting = None
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page_html, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            posting = data
            break
    title_m = re.search(r'data-qa="vacancy-title"[^>]*>(.*?)</h1>', page_html, re.S)
    title = (posting or {}).get("title") or (_text(title_m.group(1)) if title_m else "")
    if not title:
        return None
    skills_found = [_text(s) for s in re.findall(r'data-qa="skills-element"[^>]*>(.*?)</li>', page_html, re.S)]
    exp_m = re.search(r'data-qa="vacancy-experience"[^>]*>(.*?)</', page_html, re.S)
    sal_m = re.search(r'data-qa="vacancy-salary"[^>]*>(.*?)</(?:div|span)>\s*</', page_html, re.S)
    salary_text = _text(sal_m.group(1)) if sal_m else ""
    lo, hi = parse_salary(salary_text)
    org = (posting or {}).get("hiringOrganization") or {}
    return {
        "url": url, "source": "hh", "title": title, "company": org.get("name", "") if isinstance(org, dict) else "",
        "skills": [s for s in skills_found if s], "experience": _text(exp_m.group(1)) if exp_m else "",
        "salary_from": lo, "salary_to": hi, "currency": currency_of(salary_text) if (lo or hi) else "",
        "description": _text((posting or {}).get("description", ""))[:6000],
    }


# ---------- cache ----------
def _key(domain: str, query_text: str, area: str) -> str:
    """The sample depends on the site and the region as much as on the query."""
    return f"{domain}|{area or DEFAULT_AREA.get(domain, '')}|{norm(query_text)}"


def _cached(key: str, grade: Grade) -> list[dict]:
    since = (datetime.now() - timedelta(hours=CACHE_HOURS)).isoformat(timespec="seconds")
    rows = query("SELECT * FROM market_vacancies WHERE query=? AND grade=? AND fetched_at >= ?", (key, grade.value, since))
    for r in rows:
        r["skills"] = json.loads(r["skills"] or "[]")
    return rows


def _store(key: str, grade: Grade, items: list[dict]) -> None:
    with transaction() as c:
        c.executemany(
            "INSERT OR REPLACE INTO market_vacancies(url, source, query, grade, title, company, skills, experience, "
            "salary_from, salary_to, currency, description, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(v["url"], v["source"], key, grade.value, v["title"], v["company"],
              json.dumps(v["skills"], ensure_ascii=False), v["experience"], v["salary_from"], v["salary_to"], v["currency"],
              v["description"], now()) for v in items],
        )


def fetch_hh(domain: str, query_text: str, grade: Grade, area: str, size: int, progress: Progress,
             get: Callable[[str], str] = _get, pause: tuple[float, float] = (0.8, 1.8)) -> tuple[list[dict], str]:
    """Up to `size` vacancies from hh; returns them and a note when hh stopped the reading early."""
    key = _key(domain, query_text, area)
    cached = _cached(key, grade)
    if len(cached) >= min(size, 10):
        progress(f"Беру {len(cached)} вакансий hh, прочитанных за последние сутки")
        return cached[:size], ""
    progress("Ищу вакансии на hh")
    try:
        ids = parse_search(get(search_url(domain, query_text, grade, area)))
    except Blocked:
        return [], "hh показал капчу при поиске, сравнение с рынком только по вакансиям из базы бота"
    except (urllib.error.URLError, TimeoutError, OSError):
        return [], "Нет связи с hh, сравнение с рынком только по вакансиям из базы бота"
    items, note = [], ""
    for i, vid in enumerate(ids[:size]):
        progress(f"Читаю вакансии hh: {i + 1} из {min(size, len(ids))}")
        url = f"https://{domain}/vacancy/{vid}"
        try:
            v = parse_vacancy(get(url), url)
        except Blocked:
            note = f"hh показал капчу, прочитано {len(items)} вакансий из {min(size, len(ids))}"
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        if v:
            items.append(v)
        time.sleep(random.uniform(*pause))
    if items:
        _store(key, grade, items)
    return items, note


def from_database(query_text: str, limit: int = 40) -> list[dict]:
    """Vacancies the bot found on other sites whose title shares a word with the role, with their skills."""
    words = [w for w in norm(query_text).replace("-", " ").split() if len(w) > 2 and w not in TITLE_STOP]
    if not words:
        return []
    rows = query("SELECT url, source, title, company, skills, experience, salary_from, salary_to, salary_text, summary "
                 "FROM vacancies WHERE skills IS NOT NULL AND skills != '' ORDER BY id DESC LIMIT 2000")
    out = []
    for r in rows:
        if any(w in norm(r["title"]) for w in words):
            out.append({"url": r["url"], "source": r["source"], "title": r["title"] or "", "company": r["company"] or "",
                        "skills": [s.strip() for s in (r["skills"] or "").split(",") if s.strip()],
                        "experience": r["experience"] or "", "salary_from": r["salary_from"], "salary_to": r["salary_to"],
                        "currency": currency_of(r["salary_text"]) if (r["salary_from"] or r["salary_to"]) else "",
                        "description": r["summary"] or ""})
            if len(out) >= limit:
                break
    return out


# ---------- aggregation ----------
def _vacancy_skills(v: dict, vocabulary: list[str]) -> set[str]:
    """Key skills as written by the employer plus known skills mentioned in the description."""
    found = {skills.canonical(s) for s in v["skills"]}
    if v.get("description"):
        found |= set(skills.find_in(v["description"], vocabulary))
    return found


def _salary(items: list[dict]) -> Salary | None:
    by_currency: dict[str, list[int]] = {}
    for v in items:
        lo, hi = v.get("salary_from"), v.get("salary_to")
        if not (lo or hi) or not v.get("currency"):
            continue
        by_currency.setdefault(v["currency"], []).append(round(((lo or hi) + (hi or lo)) / 2))
    if not by_currency:
        return None
    currency, values = max(by_currency.items(), key=lambda kv: len(kv[1]))
    if len(values) < 3:
        return None
    values.sort()
    q1, q2, q3 = quantiles(values, n=4)
    return Salary(currency=currency, low=int(round(q1, -3)), median=int(round(q2, -3)), high=int(round(q3, -3)), count=len(values))


def aggregate(items: list[dict], resume_text: str, query_text: str, note: str = "") -> Market:
    vocabulary = sorted({skills.canonical(s) for v in items for s in v["skills"]})
    counts: Counter[str] = Counter()
    for v in items:
        counts.update(_vacancy_skills(v, vocabulary))
    n = len(items)
    top = [(name, c) for name, c in counts.most_common()
           if c >= 2 and c * 100 / max(n, 1) >= 10 and not skills.is_generic(name)][:25]
    market_skills = [MarketSkill(name=name, share=round(c * 100 / n), have=skills.covers(resume_text, name)) for name, c in top]
    weight = sum(s.share for s in market_skills[:15])
    coverage = round(sum(s.share for s in market_skills[:15] if s.have) * 100 / weight) if weight else 0
    words: Counter[str] = Counter()
    for v in items:
        words.update({w for w in re.findall(r"[\w#+.]+", v["title"].lower()) if len(w) > 1 and w not in TITLE_STOP})
    return Market(
        query=query_text, sample_size=n, sources=sorted({v["source"] for v in items}), note=note,
        skills=market_skills, coverage=coverage, salary=_salary(items),
        title_words=[w for w, c in words.most_common(8) if c >= 2],
        examples=[MarketVacancyRef(title=v["title"], company=v["company"], url=v["url"], source=v["source"]) for v in items[:8]],
    )


def collect(domain: str, query_text: str, grade: Grade, area: str, size: int, resume_text: str, progress: Progress,
            get: Callable[[str], str] = _get) -> Market | None:
    hh_items, note = fetch_hh(domain, query_text, grade, area, size, progress, get=get)
    seen = {v["url"] for v in hh_items}
    extra = [v for v in from_database(query_text) if v["url"] not in seen]
    items = hh_items + extra
    if len(items) < 3:
        return Market(query=query_text, sample_size=len(items), note=note or "Подходящих вакансий почти нет: уточните роль")
    if len(items) < 10 and not note:
        note = (f"Нашлось всего {len(items)} вакансий: выводы примерные. Попробуйте роль короче, например "
                f"«{short_role(query_text)}», или выберите регион шире в настройках hh")
    return aggregate(items, resume_text, query_text, note)


def short_role(query_text: str) -> str:
    """«Backend-разработчик Python» → «Python»: the technology finds more vacancies than the full title."""
    tech = skills.find_in(query_text)
    return tech[0] if tech else query_text.split()[0]
