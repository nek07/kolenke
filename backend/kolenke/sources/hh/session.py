"""Your hh login: sign in once in the browser window, the session stays in the browser profile."""
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from kolenke.db.repositories import settings
from kolenke.db.repositories.events import log
from kolenke.schemas.settings import HhResume
from kolenke.sources.browser import hh_window
from kolenke.workers.runner import runner

NOT_LOGGED_IN = "hh: вы не вошли в аккаунт — нажмите «Войти в hh»"


def is_logged_in(page: Page, domain: str) -> bool:
    page.goto(f"https://{domain}/applicant/resumes", wait_until="domcontentloaded")
    return "login" not in page.url and "account" not in page.url


@contextmanager
def logged_in_page() -> Iterator[tuple[Page, str] | None]:
    """(page, domain) in a window signed in to hh, or None (already logged) when you are not signed in."""
    domain = settings.get().hh_domain
    with hh_window() as (_, page):
        if not is_logged_in(page, domain):
            log(NOT_LOGGED_IN)
            yield None
        else:
            yield page, domain


def login() -> None:
    domain = settings.get().hh_domain
    with hh_window() as (ctx, page):
        page.goto(f"https://{domain}/account/login", wait_until="domcontentloaded")
        log("Окно браузера открыто: войдите в свой аккаунт hh — окно закроется само после входа")
        closed = {"v": False}
        ctx.on("close", lambda *_: closed.update(v=True))
        for _ in range(600):  # up to 20 min
            if closed["v"] or runner.stop_requested:
                break
            try:
                page.wait_for_timeout(2000)
                # hh sets hhrole=applicant once the job seeker is signed in
                if any(c["name"] == "hhrole" and c["value"] == "applicant" for c in ctx.cookies()):
                    log("hh: вход выполнен ✓")
                    _load_resumes(page, domain)
                    break
            except Exception:
                break
    log("Окно входа закрыто. Сессия сохранена в профиле браузера")


def _load_resumes(page: Page, domain: str) -> list[HhResume]:
    """Read your resumes from hh and remember them for the resume-based search."""
    page.goto(f"https://{domain}/applicant/resumes", wait_until="domcontentloaded")
    try:
        page.locator('a[data-qa^="resume-card-link-"]').first.wait_for(timeout=10000)
    except PWTimeout:
        log("hh: не нашёл резюме в аккаунте")
        return []
    resumes = [HhResume(**r) for r in page.evaluate(
        """() => [...document.querySelectorAll('a[data-qa^="resume-card-link-"]')].map(a => {
            const lines = a.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
            return {hash: a.dataset.qa.replace('resume-card-link-', ''), title: lines[1] || lines[0] || ''};
        })"""
    )]
    values: dict = {"hh_resumes": resumes}
    if resumes and settings.get().hh_resume_hash not in [r.hash for r in resumes]:
        values["hh_resume_hash"] = resumes[0].hash
    settings.save(values)
    log("hh: резюме в аккаунте: " + ", ".join(r.title for r in resumes))
    return resumes


def load_resumes() -> None:
    with logged_in_page() as session:
        if session:
            _load_resumes(*session)


def check_login() -> bool:
    with logged_in_page() as session:
        if session:
            _load_resumes(*session)
            log("hh: вход выполнен ✓")
    return session is not None
