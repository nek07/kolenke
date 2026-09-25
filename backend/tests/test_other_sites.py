"""Хабр Карьера и Enbek: contacts, place, currency, page readers on saved pages, filters, monitoring, «В письма компаниям»."""
import json
import re
from contextlib import contextmanager

import pytest
from conftest import FIXTURES, add_vacancy

from kolenke.db.connection import query, scalar
from kolenke.db.repositories import settings
from kolenke.sources.boards import REGISTRY, enbek, habr, monitor, parsing


# ---------- contacts ----------
def test_extract_contacts():
    text = ("Пишите на HR@Irlix.com или jobs@company.kz. Телефон: 8 (701) 123-45-67, +7 727 258 52 02. "
            "Telegram: @irlix_hr, t.me/company_jobs. Логотип logo@2x.png, noreply@company.kz")
    c = parsing.extract_contacts(text)
    assert c["emails"] == ["hr@irlix.com", "jobs@company.kz"]
    assert c["phones"] == ["+7 701 123 45 67", "+7 727 258 52 02"]
    assert set(c["telegram"]) == {"@company_jobs", "@irlix_hr"}


def test_merge_contacts_dedupes_and_keeps_person():
    m = parsing.merge_contacts({"emails": ["a@x.kz"], "person": "Айгерим"},
                               {"emails": ["a@x.kz", "b@x.kz"], "phones": ["+7 700 000 00 00"]})
    assert m == {"emails": ["a@x.kz", "b@x.kz"], "phones": ["+7 700 000 00 00"], "telegram": [], "person": "Айгерим"}


# ---------- place & money ----------
@pytest.mark.parametrize("places, remote, country", [
    (["Алматы"], False, "Казахстан"), (["г. Астана"], False, "Казахстан"), (["Москва", "Санкт-Петербург"], True, "Россия"),
    (["Минск"], False, "Беларусь"), ([], True, "Удалённо"), ([], False, ""), (["Московская область"], False, ""),
])
def test_country_of(places, remote, country):
    assert parsing.country_of(places, remote) == country


@pytest.mark.parametrize("text, cur", [("от 150 000 ₽", "RUB"), ("до 3 000 $", "USD"), ("от 455 000 тг.", "KZT"),
                                       ("от 800 000 тенге", "KZT"), ("", ""), (None, "")])
def test_currency_of(text, cur):
    assert parsing.currency_of(text) == cur


def test_summarize_decodes_entities_and_cuts():
    assert parsing.summarize("Обязанности: &middot; Java") == "Обязанности: · Java"
    long = "слово " * 100
    assert len(parsing.summarize(long)) <= 281 and parsing.summarize(long).endswith("…")


@pytest.mark.parametrize("text, tidy", [("от 800 000 до 800 000 тенге", "800 000 тенге"),
                                        ("от 800 000 до 1 200 000 тенге", "от 800 000 до 1 200 000 тенге"),
                                        ("от 455 000 тг.", "от 455 000 тг."), (None, None)])
def test_tidy_salary(text, tidy):
    assert parsing.tidy_salary(text) == tidy


def test_registry_boards_follow_the_protocol():
    for key, board in REGISTRY.items():
        assert board.key == key and board.name and callable(board.search) and callable(board.details)


# ---------- page readers on saved real pages ----------
@pytest.fixture(scope="module")
def browser_page():
    """The saved pages reference the sites' scripts and images: block the network so the tests are offline and fast."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.route(re.compile(r"^https?://"), lambda route: route.abort())
        yield page
        b.close()


def load(page, name):
    """Only the DOM is needed: don't wait for images and frames of the saved page."""
    page.set_content((FIXTURES / name).read_text(), wait_until="domcontentloaded")


def test_habr_list_page(browser_page):
    load(browser_page, "habr_list.html")
    items = [habr.normalize(r) for r in browser_page.evaluate(habr.LIST_JS)]
    assert len(items) >= 5
    assert all(v["ext_id"] and v["url"].startswith("https://career.habr.com/vacancies/") for v in items)
    assert not any("Похожие" in (v["salary_text"] or "") for v in items)  # the forecast is never taken for a salary
    assert any(v["salary_text"] for v in items)
    assert any(v["country"] == "Россия" and v["remote"] for v in items)


def test_habr_vacancy_page(browser_page):
    load(browser_page, "habr_vacancy.html")
    assert len(browser_page.evaluate(habr.DETAIL_JS)["text"]) > 100


def test_enbek_list_page(browser_page):
    load(browser_page, "enbek_list.html")
    items = [enbek.normalize(r) for r in browser_page.evaluate(enbek.LIST_JS)]
    assert items and all(v["country"] == "Казахстан" and v["ext_id"] for v in items)
    first = items[0]
    assert first["title"] == "Team Lead Backend Developer"  # the employer's title, not the classifier profession
    assert first["skills"].startswith("профессия:") and "455 000" in first["salary_text"]


def test_enbek_vacancy_page(browser_page):
    load(browser_page, "enbek_vacancy.html")
    d = browser_page.evaluate(enbek.DETAIL_JS)
    assert d["emails"] and d["person"] and len(d["phones_raw"]) >= 10
    assert "000" in d["salary"]


# ---------- filters ----------
def s_with(**over):
    return settings.get().model_copy(update={"other_query": "backend", **over})


def vac(**kw):
    v = {"source": "habr", "title": "Backend", "company": "X", "salary_text": None, "remote": 0, "country": "Россия"}
    v.update(kw)
    return v


def test_foreign_currency_is_not_compared_with_tenge_floor():
    ok, _, reasons = monitor.evaluate(vac(salary_text="от 150 000 ₽"), s_with(f_salary_min=400000), set())
    assert ok and any("RUB" in r["text"] for r in reasons)
    assert not monitor.evaluate(vac(source="enbek", salary_text="от 300 000 тг.", country="Казахстан"),
                                s_with(f_salary_min=400000), set())[0]


def test_country_filter():
    s = s_with(other_countries="Казахстан, удалённо")
    assert monitor.evaluate(vac(country="Казахстан"), s, set())[0]
    assert monitor.evaluate(vac(country="Россия", remote=1), s, set())[0]
    ok, note, _ = monitor.evaluate(vac(country="Россия"), s, set())
    assert not ok and "Россия" in note
    assert monitor.evaluate(vac(country="Россия"), s_with(other_countries=""), set())[0]


def test_place_filter_accepts_cities():
    s = s_with(other_countries="астана")
    assert monitor.evaluate(vac(source="enbek", country="Казахстан", location="г.Астана"), s, set())[0]
    ok, note, _ = monitor.evaluate(vac(source="enbek", country="Казахстан", location="г. Алматы, Медеуский район"), s, set())
    assert not ok and "Алматы" in note


# ---------- monitoring without network ----------
class FakePage:
    def wait_for_timeout(self, ms):
        pass


@contextmanager
def fake_headless_page():
    yield FakePage()


class FakeBoard:
    def __init__(self, key, name, items, details):
        self.key, self.name, self.items, self._details = key, name, items, details

    def search(self, page, query, pages):
        return [dict(v) for v in self.items]

    def details(self, page, v, cache):
        self._details(v)


@pytest.fixture
def boards(monkeypatch):
    """Replaces the real boards with FakeBoard instances: returns a setter taking {key: FakeBoard}."""
    monkeypatch.setattr(monitor.browser, "headless_page", fake_headless_page)

    def use(**fakes):
        for key, fake in fakes.items():
            monkeypatch.setitem(REGISTRY, key, fake)
    return use


def test_monitor_saves_once_with_contacts_and_filters(boards):
    settings.save({"other_query": "backend", "other_sites": ["habr", "enbek"], "hh_exclude": "senior"})
    boards(
        habr=FakeBoard("habr", "Хабр Карьера", [
            habr.normalize({"href": "/vacancies/1", "title": "Backend", "company": "IRLIX", "chips": ["Middle", "Можно удалённо"]}),
            habr.normalize({"href": "/vacancies/2", "title": "Senior Backend", "company": "Y", "chips": ["Москва"]})],
            lambda v: v.update(summary="Go", contacts=parsing.merge_contacts({"emails": ["hr@irlix.com"]}))),
        enbek=FakeBoard("enbek", "Enbek", [
            enbek.normalize({"href": "/ru/vacancy/x~9", "title": "Разработчик", "subtitle": "Middle Backend", "company": "KMF",
                             "location": "г. Алматы"})],
            lambda v: v.update(summary="Java", salary_text="от 800 000 тг.",
                               contacts=parsing.merge_contacts({"emails": ["cv@kmf.kz"], "person": "Лаура"}))),
    )
    assert monitor.monitor() == 2  # «Senior Backend» is excluded by the shared hh filter
    rows = {r["title"]: r for r in query("SELECT * FROM vacancies")}
    assert rows["Senior Backend"]["status"] == "skipped"
    assert json.loads(rows["Middle Backend"]["contacts"])["person"] == "Лаура"
    assert rows["Middle Backend"]["salary_from"] == 800000 and rows["Middle Backend"]["country"] == "Казахстан"
    assert monitor.monitor() == 0 and scalar("SELECT COUNT(*) FROM vacancies") == 3  # nothing twice


def test_monitor_needs_query_and_sites():
    settings.save({"other_query": "", "desired_position": "", "hh_query": "", "other_sites": ["habr"]})
    assert monitor.monitor() == 0
    assert "укажите запрос" in query("SELECT msg FROM log ORDER BY id DESC LIMIT 1")[0]["msg"]


def test_monitor_respects_vacancies_per_check(boards):
    opened = []
    settings.save({"other_query": "backend", "other_sites": ["habr"], "other_max_details": 1})
    items = [habr.normalize({"href": f"/vacancies/{i}", "title": f"Backend {i}", "company": "X", "chips": []}) for i in range(3)]
    boards(habr=FakeBoard("habr", "Хабр Карьера", items, lambda v: opened.append(v["url"])))
    monitor.monitor()
    assert len(opened) == 1 and scalar("SELECT COUNT(*) FROM vacancies") == 3  # all saved, one page opened
    settings.save({"other_max_details": 0})
    items[:] = [habr.normalize({"href": "/vacancies/9", "title": "Backend 9", "company": "X", "chips": []})]
    monitor.monitor()
    assert len(opened) == 1  # 0 = only the lists


# ---------- to «Письма компаниям» ----------
def test_to_companies(client):
    a = add_vacancy(ext_id="1", source="enbek", url="https://www.enbek.kz/ru/vacancy/a~1", company="KMF", title="Backend",
                    contacts=json.dumps({"emails": ["cv@kmf.kz", "hr@kmf.kz"]}))
    b = add_vacancy(ext_id="2", source="habr", url="https://career.habr.com/vacancies/2", contacts=json.dumps({"emails": []}))
    assert client.post("/api/vacancies/to-companies", json={"ids": [a, b]}).json() == {"added": 2, "no_email": 1}
    assert client.post("/api/vacancies/to-companies", json={"ids": [a]}).json() == {"added": 0, "no_email": 0}
    rows = client.get("/api/companies").json()
    assert {(r["name"], r["email"], r["position"]) for r in rows} == {("KMF", "cv@kmf.kz", "Backend"), ("KMF", "hr@kmf.kz", "Backend")}
    assert query("SELECT kind FROM events WHERE vacancy_id=?", (a,)) == [{"kind": "contact"}]
