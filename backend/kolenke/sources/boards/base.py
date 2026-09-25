"""Read-only job boards: no login and no «Откликнуться», only vacancies with their salary, place and contacts.

A new board is one module with a class implementing `Board`, added to REGISTRY in sources/boards/__init__.py."""
from typing import Protocol

from playwright.sync_api import Page

Vacancy = dict  # normalized: source, ext_id, url, title, company, salary_text, location, country, remote, ...


class Board(Protocol):
    key: str   # stored in vacancies.source and in the «other_sites» setting
    name: str  # shown to you

    def search(self, page: Page, query: str, pages: int) -> list[Vacancy]:
        """Result pages 1..pages, normalized."""

    def details(self, page: Page, v: Vacancy, cache: dict) -> None:
        """Opens the vacancy page and fills v["summary"], v["contacts"] (and anything else it can read).
        cache lives for one monitoring run, e.g. for company pages shared by several vacancies."""


def goto(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
