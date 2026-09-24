"""The page itself: JS syntax, references between HTML and JS, and a real headless browser run on a test server."""
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

import db
from conftest import ROOT, add_vacancy

HTML = (ROOT / "static" / "index.html").read_text()
SCRIPT = HTML[HTML.index("<script>") + 8: HTML.rindex("</script>")]


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_js_syntax(tmp_path):
    f = tmp_path / "page.js"
    f.write_text(SCRIPT)
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_referenced_id_exists():
    ids = set(re.findall(r'\bid="([\w-]+)"', HTML))
    used = set(re.findall(r"\$\('#([\w-]+)'\)", SCRIPT)) | set(re.findall(r"getElementById\('([\w-]+)'\)", SCRIPT))
    assert not used - ids, f"JS uses missing elements: {sorted(used - ids)}"


def test_every_inline_handler_function_is_defined():
    defined = set(re.findall(r"(?:async\s+)?function\s+(\w+)\s*\(", SCRIPT)) | set(re.findall(r"(?:const|let)\s+(\w+)\s*=", SCRIPT))
    called = set()
    for handler in re.findall(r'on(?:click|change|keydown|input)="([^"]+)"', HTML):
        called |= set(re.findall(r"(?<![\w.$])([a-zA-Z_]\w*)\s*\(", handler))
    builtin = {"if", "setTimeout", "event", "confirm"}
    assert not called - defined - builtin, f"handlers call undefined functions: {sorted(called - defined - builtin)}"


def test_no_employer_text_inside_js_source():
    """Employer-controlled text must never be pasted into inline JS (the old onclick='...JSON.stringify(q.text)' hole)."""
    assert not re.search(r"on\w+='[^']*JSON\.stringify", SCRIPT)


def test_requests_carry_the_jobbot_header():
    api = SCRIPT[SCRIPT.index("async function api("):]
    api = api[:api.index("\n}")]
    assert api.count("'X-JobBot':'1'") == 2  # JSON bodies and file uploads


# ---------- real browser ----------
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server():
    port = free_port()
    env = {**os.environ, "JOBBOT_DATA": os.environ["JOBBOT_DATA"], "JOBBOT_NO_BACKGROUND": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--port", str(port), "--no-access-log"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(5)


@pytest.fixture
def page(server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 860})
        pg.errors, pg.bad = [], []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and "fonts.g" not in m.text and pg.errors.append(m.text))
        pg.on("response", lambda r: "/api/" in r.url and r.status >= 400 and pg.bad.append(f"{r.status} {r.url}"))
        yield pg
        browser.close()


def seed():
    db.set_settings({"full_name": "Аня Тест", "hh_resumes": '[{"hash": "h1", "title": "Backend"}]', "hh_resume_hash": "h1"})
    add_vacancy(ext_id="1", title="Новая <b>вакансия</b>", company="ТОО «Кавычки'\"»")
    add_vacancy(ext_id="2", title="Отправленная", status="applied", applied_at=db.now(), hh_state="просмотрен")
    add_vacancy(ext_id="3", title="Отказ", status="applied", applied_at=db.now(), hh_state="отказ")
    db.x("INSERT INTO questions(text, source, created_at) VALUES (?, 'form', ?)", ("Ваш опыт с 'SQL'?<img src=x onerror=alert(1)>", db.now()))


TABS = ["dash", "hh", "pipe", "chats", "mail", "other", "answers", "stats", "settings"]


def test_every_tab_opens_without_errors(page, server):
    seed()
    page.goto(server)
    page.wait_for_selector("#greet")
    for t in TABS:
        page.click(f'nav button[data-t="{t}"]')
        page.wait_for_timeout(400)
        assert page.is_visible(f"section#{t}"), t
    assert not page.errors, page.errors
    assert not page.bad, page.bad


def test_hostile_text_is_shown_as_text(page, server):
    seed()
    alerts = []
    page.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
    page.goto(server)
    page.click('nav button[data-t="hh"]')
    page.wait_for_selector("#hhtable tr")
    assert "Новая <b>вакансия</b>" in page.inner_text("#hhtable")
    page.click('nav button[data-t="answers"]')
    page.wait_for_timeout(500)
    page.click("#qtable button:has-text('Ответить')")
    assert page.input_value("#anstable .ans .topic").startswith("Ваш опыт с 'SQL'")
    assert not alerts and not page.errors


def test_gentle_rejection_wording(page, server):
    seed()
    page.goto(server)
    page.click('nav button[data-t="hh"]')
    page.click("#hhchips button:has-text('Отправлены')")
    page.wait_for_timeout(300)
    table = page.inner_text("#hhtable")
    assert "не сейчас" in table and "отказ" not in table.replace("Отказ\n", "")  # the title «Отказ» itself is fine


def test_pipeline_drag_and_drawer(page, server):
    seed()
    page.goto(server)
    page.click('nav button[data-t="pipe"]')
    page.wait_for_selector(".pcard")
    card = page.locator(".pcard", has_text="Отправленная")
    card.drag_to(page.locator('.col[data-stage="interview"]'))
    page.wait_for_timeout(500)
    assert db.q("SELECT stage FROM vacancies WHERE ext_id='2'")[0]["stage"] == "interview"
    page.locator(".pcard", has_text="Отправленная").click()
    page.wait_for_selector("#panel .stagepick")
    page.fill("#nxStep", "Собеседование")
    page.fill("#nxAt", "2030-01-01T15:00")
    page.click("#panel button:has-text('Сохранить')")
    page.wait_for_timeout(500)
    row = db.q("SELECT next_step, next_at FROM vacancies WHERE ext_id='2'")[0]
    assert row == {"next_step": "Собеседование", "next_at": "2030-01-01T15:00:00"}
    assert not page.errors and not page.bad


def test_phone_width_has_no_horizontal_scroll(server):
    from playwright.sync_api import sync_playwright
    seed()
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 375, "height": 812})
        pg.goto(server)
        pg.wait_for_selector("#greet")
        for t in ["dash", "hh", "answers", "settings"]:
            pg.evaluate(f"showTab('{t}')")
            pg.wait_for_timeout(200)
            wide = pg.evaluate("""[...document.querySelectorAll('section.on *')].filter(e => e.offsetParent && e.getBoundingClientRect().right > innerWidth + 1)
                .map(e => e.tagName + '.' + (e.className || '').toString().split(' ')[0] + ' «' + (e.innerText || '').slice(0, 25) + '» → ' + Math.round(e.getBoundingClientRect().right))""")
            assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"{t}: {wide[:6]}"
        b.close()


def test_other_sites_tab_contacts_to_companies(page, server):
    import json as _json
    add_vacancy(ext_id="h1", source="habr", url="https://career.habr.com/vacancies/h1", title="Java Backend", company="IRLIX",
                salary_text="от 150 000 ₽", location="Москва", country="Россия", remote=1, summary="Микросервисы на Spring",
                contacts=_json.dumps({"emails": ["hr@irlix.com"], "phones": ["+7 996 953 98 87"], "telegram": ["@IRLIX_hub"]}))
    add_vacancy(ext_id="e1", source="enbek", url="https://www.enbek.kz/ru/vacancy/x~1", title="Middle Backend", company="KMF",
                salary_text="от 800 000 тг.", location="г. Алматы", country="Казахстан", contacts=_json.dumps({"emails": []}))
    page.goto(server)
    page.click('nav button[data-t="other"]')
    page.wait_for_selector("#otable tr[data-id]")
    text = page.inner_text("#otable")
    assert "hr@irlix.com" in text and "от 150 000 ₽" in text and "можно удалённо" in text
    page.check("#oOnlyEmail")
    page.wait_for_timeout(300)
    assert page.locator("#otable tr[data-id]").count() == 1
    page.locator("#otable input[type=checkbox]").first.check()
    page.click("#osel button:has-text('В письма компаниям')")
    page.wait_for_timeout(400)
    assert db.q("SELECT name, email, position FROM companies") == [{"name": "IRLIX", "email": "hr@irlix.com", "position": "Java Backend"}]
    page.locator("#otable tr[data-id]").first.click()
    page.wait_for_selector("#panel .cts")
    assert "+7 996 953 98 87" in page.inner_text("#panel")
    assert not page.errors and not page.bad, (page.errors, page.bad)


def test_other_sites_settings_are_reflected(page, server):
    db.set_settings({"other_sites": "enbek", "hh_query": "backend разработчик", "other_query": ""})
    page.goto(server)
    page.click('nav button[data-t="other"]')
    page.wait_for_timeout(500)
    on = page.eval_on_selector_all("#osrcpick .chip.on", "els => els.map(e => e.dataset.v)")
    assert on == ["enbek"]
    assert "backend разработчик" in page.get_attribute("#oquery", "placeholder")
    page.click("#osrcpick .chip[data-v='habr']")
    page.wait_for_timeout(500)
    assert db.get_settings()["other_sites"] == "enbek,habr"
