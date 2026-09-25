"""Хабр Карьера (career.habr.com)."""
import re
from urllib.parse import quote

from playwright.sync_api import Page

from kolenke.sources.boards.base import Vacancy, goto
from kolenke.sources.boards.parsing import country_of, extract_contacts, merge_contacts, summarize

BASE = "https://career.habr.com"
LEVELS = ("Intern", "Junior", "Middle", "Senior", "Lead")

LIST_JS = """() => [...document.querySelectorAll('.vacancy-card')].map(c => {
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

DETAIL_JS = """() => {
    const d = document.querySelector('.vacancy-description__text');
    const comp = document.querySelector('.company_name a, a[href^="/companies/"]');
    return {text: d ? d.innerText : '', company_href: comp ? comp.getAttribute('href') : ''};
}"""


def normalize(raw: dict) -> Vacancy:
    chips = raw.get("chips") or []
    remote = any("удал" in c.lower() for c in chips)
    level = next((c for c in chips if c in LEVELS), "")
    places = [c for c in chips if c not in LEVELS and "удал" not in c.lower() and "полный" not in c.lower()]
    m = re.search(r"/vacancies/(\d+)", raw.get("href") or "")
    return {
        "source": "habr", "ext_id": m.group(1) if m else None, "url": BASE + (raw.get("href") or ""),
        "title": raw.get("title", ""), "company": raw.get("company", ""),
        "company_url": (BASE + raw["company_href"]) if raw.get("company_href") else "",
        "salary_text": raw.get("salary") or None, "experience": level or None, "remote": int(remote),
        "location": ", ".join(places), "country": country_of(places, remote),
        "skills": ", ".join(raw.get("skills") or []),
    }


class Habr:
    key = "habr"
    name = "Хабр Карьера"

    def search(self, page: Page, query: str, pages: int) -> list[Vacancy]:
        found = []
        for n in range(1, pages + 1):
            goto(page, f"{BASE}/vacancies?q={quote(query)}&type=all&page={n}")
            items = page.evaluate(LIST_JS)
            if not items:
                break
            found += [normalize(r) for r in items]
        return found

    def details(self, page: Page, v: Vacancy, cache: dict) -> None:
        goto(page, v["url"])
        try:  # the description is rendered a moment after the page
            page.wait_for_function(
                "() => (document.querySelector('.vacancy-description__text')?.innerText || '').trim().length > 0", timeout=4000)
        except Exception:
            pass
        d = page.evaluate(DETAIL_JS)
        v["summary"] = summarize(d["text"]) or (f"Навыки: {v['skills']}" if v.get("skills") else "Работодатель не заполнил описание")
        contacts = [extract_contacts(d["text"])]
        curl = v.get("company_url") or ((BASE + d["company_href"]) if d.get("company_href") else "")
        if curl:
            v["company_url"] = curl
            if curl not in cache:  # HR e-mails usually live on the company page
                try:
                    goto(page, curl)
                    cache[curl] = extract_contacts(page.evaluate("document.body.innerText"))
                except Exception:
                    cache[curl] = {}
            contacts.append(cache[curl])
        v["contacts"] = merge_contacts(*contacts)
