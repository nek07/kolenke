"""Smart filters for vacancies. Every check explains itself, so the side panel can show why a vacancy passed."""
import re

from kolenke.db.repositories import vacancies
from kolenke.schemas.enums import EXPERIENCE_LABELS
from kolenke.schemas.settings import AppSettings
from kolenke.services.text import norm, split_list

Reason = dict  # {"ok": bool, "text": str}


def parse_salary(text: str | None) -> tuple[int | None, int | None]:
    """«от 300 000 до 500 000 ₸ за месяц» → (300000, 500000); «до 1 000 $» → (None, 1000)."""
    if not text:
        return None, None
    t = text.lower().replace("\u202f", " ").replace("\xa0", " ")
    nums = [int(n.replace(" ", "")) for n in re.findall(r"\d[\d ]*\d|\d", t)]
    if not nums:
        return None, None
    if len(nums) >= 2:
        return nums[0], nums[1]
    if re.search(r"\bдо\s*\d", t) and not re.search(r"\bот\s*\d", t):
        return None, nums[0]
    return nums[0], None


def rejected_companies() -> set[str]:
    """Companies that already answered «отказ» on hh."""
    return {norm(c) for c in vacancies.rejected_companies()}


def rejected_if_enabled(s: AppSettings) -> set[str]:
    return rejected_companies() if s.f_skip_rejected else set()


def check(v: dict, s: AppSettings, rejected: set[str], source: str = "") -> tuple[bool, str | None, list[Reason]]:
    """Returns (passed, note, reasons). note = the first failed check."""
    reasons: list[Reason] = [{"ok": True, "text": source}] if source else []
    fail = None

    def add(ok: bool, text: str):
        nonlocal fail
        reasons.append({"ok": ok, "text": text})
        if not ok and fail is None:
            fail = text

    title = norm(v.get("title"))
    words = [w for w in split_list(s.hh_exclude) if w in title]
    if words:
        add(False, f"в названии есть «{words[0]}»")

    lo, hi = v.get("salary_from"), v.get("salary_to")
    floor = s.f_salary_min or 0
    if lo is None and hi is None:
        if s.f_skip_no_salary:
            add(False, "зарплата не указана")
        elif floor:
            add(True, "зарплата не указана (без зарплаты не отсеиваем)")
    else:
        top = hi or lo
        if floor and top < floor:
            add(False, f"зарплата {v.get('salary_text') or top} ниже {floor:,}".replace(",", " "))
        else:
            add(True, f"зарплата {v.get('salary_text')}" + (f" не ниже {floor:,}".replace(",", " ") if floor else ""))

    if s.f_experience:
        add(True, "опыт: " + ", ".join(EXPERIENCE_LABELS[c] for c in s.f_experience) + " (фильтр поиска hh)"
            + (f", в вакансии: {v['experience']}" if v.get("experience") else ""))
    elif v.get("experience"):
        add(True, f"опыт: {v['experience']}")

    company = norm(v.get("company"))
    excluded = split_list(s.f_exclude_companies)
    banned = [c for c in excluded if company and c in company]
    if banned:
        add(False, f"компания в списке исключений («{banned[0]}»)")
    elif excluded:
        add(True, "компании нет в исключениях")

    if s.f_skip_rejected:
        if company and company in rejected:
            add(False, "эта компания уже отказала вам раньше")
        else:
            add(True, "отказов от этой компании не было")

    match, need = v.get("skill_match"), s.f_min_match
    if match is None:
        if need:
            add(True, "совпадение навыков: hh не показал (не отсеиваем)")
    elif match < need:
        add(False, f"совпадение навыков {match}% меньше {need}%")
    else:
        add(True, f"совпадение навыков {match}%" + (f" (нужно от {need}%)" if need else ""))

    return fail is None, fail, reasons
