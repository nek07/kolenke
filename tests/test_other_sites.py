"""Хабр Карьера и Enbek: contacts, place, currency, page readers on saved pages, filters, monitoring, «В письма компаниям»."""
import json
from contextlib import contextmanager

import pytest

import db
import other_sites as o
from conftest import ROOT, add_vacancy

FX = ROOT / "tests" / "fixtures"


# ---------- contacts ----------
def test_extract_contacts():
    text = ("Пишите на HR@Irlix.com или jobs@company.kz. Телефон: 8 (701) 123-45-67, +7 727 258 52 02. "
            "Telegram: @irlix_hr, t.me/company_jobs. Логотип logo@2x.png, noreply@company.kz")
    c = o.extract_contacts(text)
    assert c["emails"] == ["hr@irlix.com", "jobs@company.kz"]
    assert c["phones"] == ["+7 701 123 45 67", "+7 727 258 52 02"]
    assert c["telegram"] == ["@company_jobs", "@irlix_hr"] or set(c["telegram"]) == {"@company_jobs", "@irlix_hr"}


def test_merge_contacts_dedupes_and_keeps_person():
    m = o.merge_contacts({"emails": ["a@x.kz"], "person": "Айгерим"}, {"emails": ["a@x.kz", "b@x.kz"], "phones": ["+7 700 000 00 00"]})
    assert m == {"emails": ["a@x.kz", "b@x.kz"], "phones": ["+7 700 000 00 00"], "telegram": [], "person": "Айгерим"}


# ---------- place & money ----------
@pytest.mark.parametrize("places, remote, country", [
    (["Алматы"], False, "Казахстан"), (["г. Астана"], False, "Казахстан"), (["Москва", "Санкт-Петербург"], True, "Россия"),
    (["Минск"], False, "Беларусь"), ([], True, "Удалённо"), ([], False, ""), (["Московская область"], False, ""),
])
def test_country_of(places, remote, country):
    assert o.country_of(places, remote) == country


@pytest.mark.parametrize("text, cur", [("от 150 000 ₽", "RUB"), ("до 3 000 $", "USD"), ("от 455 000 тг.", "KZT"),
                                       ("от 800 000 тенге", "KZT"), ("", ""), (None, "")])
def test_currency_of(text, cur):
    assert o.currency_of(text) == cur


def test_summarize_decodes_entities_and_cuts():
    assert o.summarize("Обязанности: &middot; Java") == "Обязанности: · Java"
    long = "слово " * 100
    assert len(o.summarize(long)) <= 281 and o.summarize(long).endswith("…")


# ---------- page readers on saved real pages ----------
@pytest.fixture(scope="module")
def browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b.new_page()
        b.close()


def test_habr_list_page(browser_page):
    browser_page.set_content((FX / "habr_list.html").read_text())
    items = [o.normalize_habr(r) for r in browser_page.evaluate(o.HABR_LIST_JS)]
    assert len(items) >= 5
    assert all(v["ext_id"] and v["url"].startswith("https://career.habr.com/vacancies/") for v in items)
    assert not any("Похожие" in (v["salary_text"] or "") for v in items)  # the forecast is never taken for a salary
    assert any(v["salary_text"] for v in items)
    assert any(v["country"] == "Россия" and v["remote"] for v in items)


def test_habr_vacancy_page(browser_page):
    browser_page.set_content((FX / "habr_vacancy.html").read_text())
    d = browser_page.evaluate(o.HABR_DETAIL_JS)
    assert len(d["text"]) > 100


def test_enbek_list_page(browser_page):
    browser_page.set_content((FX / "enbek_list.html").read_text())
    items = [o.normalize_enbek(r) for r in browser_page.evaluate(o.ENBEK_LIST_JS)]
    assert items and all(v["country"] == "Казахстан" and v["ext_id"] for v in items)
    first = items[0]
    assert first["title"] == "Team Lead Backend Developer"  # the employer's title, not the classifier profession
    assert first["skills"].startswith("профессия:") and "455 000" in first["salary_text"]


def test_enbek_vacancy_page(browser_page):
    browser_page.set_content((FX / "enbek_vacancy.html").read_text())
    d = browser_page.evaluate(o.ENBEK_DETAIL_JS)
    assert d["emails"] and d["person"] and len(d["phones_raw"]) >= 10
    assert "000" in d["salary"]


# ---------- filters ----------
def settings(**over):
    s = db.get_settings()
    s.update({"other_query": "backend"}, **over)
    return s


def vac(**kw):
    v = {"source": "habr", "title": "Backend", "company": "X", "salary_text": None, "remote": 0, "country": "Россия"}
    v.update(kw)
    return v


def test_foreign_currency_is_not_compared_with_tenge_floor():
    ok, _, reasons = o.evaluate(vac(salary_text="от 150 000 ₽"), settings(f_salary_min="400000"), set())
    assert ok and any("RUB" in r["text"] for r in reasons)
    assert not o.evaluate(vac(source="enbek", salary_text="от 300 000 тг.", country="Казахстан"), settings(f_salary_min="400000"), set())[0]


def test_country_filter():
    s = settings(other_countries="Казахстан, удалённо")
    assert o.evaluate(vac(country="Казахстан"), s, set())[0]
    assert o.evaluate(vac(country="Россия", remote=1), s, set())[0]
    ok, note, _ = o.evaluate(vac(country="Россия"), s, set())
    assert not ok and "Россия" in note
    assert o.evaluate(vac(country="Россия"), settings(other_countries=""), set())[0]


def test_place_filter_accepts_cities():
    s = settings(other_countries="астана")
    assert o.evaluate(vac(source="enbek", country="Казахстан", location="г.Астана"), s, set())[0]
    ok, note, _ = o.evaluate(vac(source="enbek", country="Казахстан", location="г. Алматы, Медеуский район"), s, set())
    assert not ok and "Алматы" in note


# ---------- monitoring without network ----------
class FakeBrowser:
    def new_context(self, **kw): return self
    def new_page(self): return self
    def wait_for_timeout(self, ms): pass
    def close(self): pass


@contextmanager
def fake_playwright():
    class P:
        class chromium:
            @staticmethod
            def launch(): return FakeBrowser()
    yield P()


def test_monitor_saves_once_with_contacts_and_filters(monkeypatch):
    db.set_settings({"other_query": "backend", "other_sites": "habr,enbek", "hh_exclude": "senior"})
    habr = [o.normalize_habr({"href": "/vacancies/1", "title": "Backend", "company": "IRLIX", "chips": ["Middle", "Можно удалённо"]}),
            o.normalize_habr({"href": "/vacancies/2", "title": "Senior Backend", "company": "Y", "chips": ["Москва"]})]
    enbek = [o.normalize_enbek({"href": "/ru/vacancy/x~9", "title": "Разработчик", "subtitle": "Middle Backend", "company": "KMF", "location": "г. Алматы"})]
    monkeypatch.setattr(o, "sync_playwright", fake_playwright)
    monkeypatch.setattr(o, "_habr", lambda page, q, n: [dict(v) for v in habr])
    monkeypatch.setattr(o, "_enbek", lambda page, q, n: [dict(v) for v in enbek])
    monkeypatch.setattr(o, "_habr_details", lambda page, v, cache: v.update(summary="Go", contacts=o.merge_contacts({"emails": ["hr@irlix.com"]})))
    monkeypatch.setattr(o, "_enbek_details", lambda page, v: v.update(summary="Java", salary_text="от 800 000 тг.", contacts=o.merge_contacts({"emails": ["cv@kmf.kz"], "person": "Лаура"})))

    assert o.monitor() == 2  # «Senior Backend» is excluded by the shared hh filter
    rows = {r["title"]: r for r in db.q("SELECT * FROM vacancies")}
    assert rows["Senior Backend"]["status"] == "skipped"
    assert json.loads(rows["Middle Backend"]["contacts"])["person"] == "Лаура"
    assert rows["Middle Backend"]["salary_from"] == 800000 and rows["Middle Backend"]["country"] == "Казахстан"
    assert o.monitor() == 0 and db.q("SELECT COUNT(*) n FROM vacancies")[0]["n"] == 3  # nothing twice


def test_monitor_needs_query_and_sites():
    db.set_settings({"other_query": "", "desired_position": "", "hh_query": "", "other_sites": "habr"})
    assert o.monitor() == 0
    assert "укажите запрос" in db.q("SELECT msg FROM log ORDER BY id DESC LIMIT 1")[0]["msg"]


# ---------- to «Письма компаниям» ----------
def test_to_companies(client):
    a = add_vacancy(ext_id="1", source="enbek", url="https://www.enbek.kz/ru/vacancy/a~1", company="KMF", title="Backend",
                    contacts=json.dumps({"emails": ["cv@kmf.kz", "hr@kmf.kz"]}))
    b = add_vacancy(ext_id="2", source="habr", url="https://career.habr.com/vacancies/2", contacts=json.dumps({"emails": []}))
    assert client.post("/api/vacancies/to_companies", json={"ids": [a, b]}).json() == {"added": 2, "no_email": 1}
    assert client.post("/api/vacancies/to_companies", json={"ids": [a]}).json() == {"added": 0, "no_email": 0}
    rows = client.get("/api/companies").json()
    assert {(r["name"], r["email"], r["position"]) for r in rows} == {("KMF", "cv@kmf.kz", "Backend"), ("KMF", "hr@kmf.kz", "Backend")}
    assert db.q("SELECT kind FROM events WHERE vacancy_id=?", (a,)) == [{"kind": "contact"}]


@pytest.mark.parametrize("text, tidy", [("от 800 000 до 800 000 тенге", "800 000 тенге"), ("от 800 000 до 1 200 000 тенге", "от 800 000 до 1 200 000 тенге"),
                                        ("от 455 000 тг.", "от 455 000 тг."), (None, None)])
def test_tidy_salary(text, tidy):
    assert o.tidy_salary(text) == tidy


def test_monitor_respects_vacancies_per_check(monkeypatch):
    opened = []
    db.set_settings({"other_query": "backend", "other_sites": "habr", "other_max_details": "1"})
    items = [o.normalize_habr({"href": f"/vacancies/{i}", "title": f"Backend {i}", "company": "X", "chips": []}) for i in range(3)]
    monkeypatch.setattr(o, "sync_playwright", fake_playwright)
    monkeypatch.setattr(o, "_habr", lambda page, q, n: [dict(v) for v in items])
    monkeypatch.setattr(o, "_habr_details", lambda page, v, cache: opened.append(v["url"]))
    o.monitor()
    assert len(opened) == 1 and db.q("SELECT COUNT(*) n FROM vacancies")[0]["n"] == 3  # all saved, one page opened
    db.set_settings({"other_max_details": "0"})
    items[:] = [o.normalize_habr({"href": "/vacancies/9", "title": "Backend 9", "company": "X", "chips": []})]
    o.monitor()
    assert len(opened) == 1  # 0 = only the lists
