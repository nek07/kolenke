"""Browser helpers shared by the sites. hh runs in a visible window with your own saved login;
job boards that need no login run headless."""
import time
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeout

from kolenke.config import get_config
from kolenke.db.repositories.events import log
from kolenke.workers.runner import runner

# Enbek blocks the default headless user agent
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")


@contextmanager
def hh_window() -> Iterator[tuple]:
    """(context, page) in the persistent profile that keeps your hh session."""
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(get_config().browser_profile_dir), headless=False, viewport={"width": 1280, "height": 860}, locale="ru-RU"
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(15000)
        try:
            yield ctx, page
        finally:
            try:
                ctx.close()
            except Exception:
                pass  # you may have closed the window yourself


@contextmanager
def headless_page() -> Iterator[Page]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            yield browser.new_context(locale="ru-RU", user_agent=USER_AGENT).new_page()
        finally:
            browser.close()


def visible(page: Page, selector: str, timeout: int = 0) -> bool:
    try:
        loc = page.locator(selector).first
        if timeout:
            loc.wait_for(state="visible", timeout=timeout)
        return loc.is_visible()
    except PWTimeout:
        return False


def screenshot(page: Page, name: str) -> str:
    """Saves a screenshot for a failure you may want to look at; returns the path to show in the log."""
    path = get_config().screens_dir / name
    page.screenshot(path=str(path))
    return f"data/screens/{path.name}"


def wait_captcha(page: Page) -> bool:
    """If hh shows a captcha, wait up to 5 minutes for you to solve it in the window."""
    def solved():
        return "captcha" not in page.url and not visible(page, '[data-qa="account-captcha-input"]')

    if solved():
        return True
    log("hh показал капчу — решите её в окне браузера, бот подождёт до 5 минут")
    for _ in range(150):
        if runner.stop_requested:
            return False
        time.sleep(2)
        if solved():
            log("Капча пройдена, продолжаю")
            return True
    return False
