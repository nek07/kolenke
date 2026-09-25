"""Enbek (enbek.kz), the state job portal of Kazakhstan."""
import re
from urllib.parse import quote

from playwright.sync_api import Page

from kolenke.sources.boards.base import Vacancy, goto
from kolenke.sources.boards.parsing import extract_contacts, merge_contacts, summarize, tidy_salary

BASE = "https://www.enbek.kz"

LIST_JS = """() => [...document.querySelectorAll('.item-list')].map(c => {
    const a = c.querySelector('a.stretched');
    const t = sel => { const e = c.querySelector(sel); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : ''; };
    return a && {
        href: a.getAttribute('href'), title: (a.innerText || a.getAttribute('title') || '').replace(/\\s+/g, ' ').trim(), subtitle: t('.subtitle'),
        company: t('.company-name') || t('.company'), location: t('li.location'), experience: t('li.experience'),
        schedule: t('li.time'), salary: t('.price'),
    };
}).filter(Boolean)"""

DETAIL_JS = """() => {
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


def normalize(raw: dict) -> Vacancy:
    m = re.search(r"~(\d+)", raw.get("href") or "")
    # the link holds the profession from the state classifier, the subtitle holds the employer's own job title
    own, profession = (raw.get("subtitle") or "").strip(), (raw.get("title") or "").strip()
    return {
        "source": "enbek", "ext_id": m.group(1) if m else None,
        "url": raw["href"] if raw.get("href", "").startswith("http") else BASE + (raw.get("href") or ""),
        "title": own or profession, "company": raw.get("company", ""), "company_url": "",
        "salary_text": raw.get("salary") or None, "experience": raw.get("experience") or None, "remote": 0,
        "location": raw.get("location", ""), "country": "Казахстан",
        "skills": f"профессия: {profession}" if own and profession != own else "",
        "schedule": raw.get("schedule", ""),
    }


class Enbek:
    key = "enbek"
    name = "Enbek"

    def search(self, page: Page, query: str, pages: int) -> list[Vacancy]:
        found = []
        for n in range(1, pages + 1):
            goto(page, f"{BASE}/ru/search/vacancy?prof={quote(query)}&page={n}")
            page.wait_for_timeout(1500)
            new = [normalize(r) for r in page.evaluate(LIST_JS)]
            if not new or (found and new[0]["url"] == found[0]["url"]):  # past the last page the site repeats page 1
                break
            found += new
        return found

    def details(self, page: Page, v: Vacancy, cache: dict) -> None:
        goto(page, v["url"])
        d = page.evaluate(DETAIL_JS)
        v["salary_text"] = tidy_salary(d["salary"] or v.get("salary_text"))
        v["summary"] = summarize(d["duties"])
        phones = extract_contacts(d["phones_raw"])["phones"]
        v["contacts"] = merge_contacts({"emails": [e.lower() for e in d["emails"]], "phones": phones, "person": d["person"]},
                                       extract_contacts(d["duties"]))
