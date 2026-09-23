"""Smart filters for hh vacancies. Every check explains itself, so the side panel can show why a vacancy passed."""
import re

import db

EXPERIENCE = {
    "noExperience": "без опыта",
    "between1And3": "1–3 года",
    "between3And6": "3–6 лет",
    "moreThan6": "более 6 лет",
}


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[«»\"'()]", "", (text or "").lower().replace("ё", "е"))).strip()


def parse_salary(text):
    """«от 300 000 до 500 000 ₸ за месяц» → (300000, 500000); «до 1 000 $» → (None, 1000)."""
    if not text:
        return None, None
    t = text.lower().replace(" ", " ").replace("\xa0", " ")
    nums = [int(n.replace(" ", "")) for n in re.findall(r"\d[\d ]*\d|\d", t)]
    if not nums:
        return None, None
    if len(nums) >= 2:
        return nums[0], nums[1]
    if "до" in t and "от" not in t:
        return None, nums[0]
    return nums[0], None


def split_list(text):
    return [norm(w) for w in re.split(r"[,\n;]", text or "") if norm(w)]


def rejected_companies():
    """Companies that already answered «отказ» on hh."""
    return {norm(r["company"]) for r in db.q("SELECT DISTINCT company FROM vacancies WHERE hh_state='отказ'") if r["company"]}


def check(v: dict, s: dict, rejected: set, source: str = ""):
    """Returns (passed, note, reasons). reasons = [{ok, text}], note = the first failed check."""
    reasons = [{"ok": True, "text": source}] if source else []
    fail = None

    def add(ok, text):
        nonlocal fail
        reasons.append({"ok": ok, "text": text})
        if not ok and fail is None:
            fail = text

    title = norm(v.get("title"))
    words = [w for w in split_list(s["hh_exclude"]) if w in title]
    if words:
        add(False, f"в названии есть «{words[0]}»")

    lo, hi = v.get("salary_from"), v.get("salary_to")
    floor = int(re.sub(r"\D", "", s["f_salary_min"] or "") or 0)
    if lo is None and hi is None:
        if s["f_skip_no_salary"] == "1":
            add(False, "зарплата не указана")
        elif floor:
            add(True, "зарплата не указана (без зарплаты не отсеиваем)")
    else:
        top = hi or lo
        if floor and top < floor:
            add(False, f"зарплата {v.get('salary_text') or top} ниже {floor:,}".replace(",", " "))
        else:
            add(True, f"зарплата {v.get('salary_text')}" + (f" не ниже {floor:,}".replace(",", " ") if floor else ""))

    wanted = [c for c in (s["f_experience"] or "").split(",") if c in EXPERIENCE]
    if wanted:
        add(True, "опыт: " + ", ".join(EXPERIENCE[c] for c in wanted) + " (фильтр поиска hh)"
            + (f", в вакансии: {v['experience']}" if v.get("experience") else ""))
    elif v.get("experience"):
        add(True, f"опыт: {v['experience']}")

    company = norm(v.get("company"))
    banned = [c for c in split_list(s["f_exclude_companies"]) if company and c in company]
    if banned:
        add(False, f"компания в списке исключений («{banned[0]}»)")
    elif split_list(s["f_exclude_companies"]):
        add(True, "компании нет в исключениях")

    if s["f_skip_rejected"] == "1":
        if company and company in rejected:
            add(False, "эта компания уже отказала вам раньше")
        else:
            add(True, "отказов от этой компании не было")

    match, need = v.get("skill_match"), int(s["f_min_match"] or 0)
    if match is None:
        if need:
            add(True, "совпадение навыков: hh не показал (не отсеиваем)")
    elif match < need:
        add(False, f"совпадение навыков {match}% меньше {need}%")
    else:
        add(True, f"совпадение навыков {match}%" + (f" (нужно от {need}%)" if need else ""))

    return fail is None, fail, reasons
