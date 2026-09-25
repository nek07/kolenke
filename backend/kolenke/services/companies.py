"""The mail list: adding companies by hand, from CSV/Excel files and from vacancies on other sites."""
import csv
import io
import json
import re

from kolenke.db.repositories import companies, events, vacancies

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def add(name: str | None, email: str, position: str | None) -> bool:
    """False for a bad e-mail or one already in the list."""
    email = (email or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return False
    return companies.add((name or "").strip(), email, (position or "").strip()) is not None


def _read_rows(filename: str, raw: bytes) -> list[list[str]]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        return [["" if c is None else str(c) for c in row] for row in wb.active.iter_rows(values_only=True)]
    text = raw.decode("utf-8-sig", errors="ignore")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def _col(header: list[str], *names: str) -> int | None:
    for i, h in enumerate(header):
        if any(n in h for n in names):
            return i
    return None


def import_file(filename: str, raw: bytes) -> int:
    """Company; e-mail; position in any column order, with or without a header. Returns how many were added.
    Raises ValueError for an empty file."""
    rows = [r for r in _read_rows(filename, raw) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("Файл пустой")
    header = [c.strip().lower() for c in rows[0]]
    ci = _col(header, "компан", "company", "назван", "name", "организ", "банк")
    ei = _col(header, "email", "e-mail", "почт", "mail")
    pi = _col(header, "должн", "позиц", "position", "ваканс")
    has_header = ei is not None and not EMAIL_RE.search(rows[0][ei] if ei < len(rows[0]) else "")
    added = 0
    for row in rows[1:] if has_header else rows:
        def cell(i, row=row):
            return row[i] if i is not None and i < len(row) else ""
        emails = EMAIL_RE.findall(cell(ei)) if has_header else []
        if not emails:
            emails = [e for c in row for e in EMAIL_RE.findall(c)]
        name = cell(ci) if has_header else next((c for c in row if c.strip() and not EMAIL_RE.search(c)), "")
        for e in emails:
            added += add(name, e, cell(pi) if has_header else "")
    return added


def from_vacancies(ids: list[int]) -> dict:
    """Put the e-mails of chosen vacancies into «Письма компаниям» (position = vacancy title)."""
    added = no_email = 0
    for vid in ids:
        v = vacancies.get(vid)
        if not v:
            continue
        emails = (json.loads(v["contacts"] or "{}")).get("emails") or []
        if not emails:
            no_email += 1
            continue
        n = sum(companies.add(v["company"], e, v["title"]) is not None for e in emails)
        added += n
        if n:
            events.add(v["id"], "contact", f"Почта добавлена в «Письма компаниям»: {', '.join(emails)}")
    return {"added": added, "no_email": no_email}
