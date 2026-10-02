"""Rule-based review: facts about the resume, the checks for the role and grade, templates for weak lines, the score.

Everything here runs locally and is deterministic, so the same resume always gets the same report and the page
can show exactly why each check passed or failed."""
import re
from dataclasses import dataclass
from datetime import date

from kolenke.schemas.enums import GRADE_LABELS, CheckStatus, Grade
from kolenke.schemas.resume import Check, Market, Recommendation, ResumeFacts, Rewrite
from kolenke.services.resume import skills
from kolenke.services.resume.profiles import GRADES, RoleProfile, grade_order, match_role
from kolenke.services.text import norm

P, W, F = CheckStatus.passed, CheckStatus.warn, CheckStatus.fail

# ---------- reading the resume ----------
SECTION_HEADS = {
    "experience": r"опыт работы|опыт|experience|work experience|карьера|места работы|трудовая деятельность",
    "skills": r"ключевые навыки|навыки|skills|hard skills|технологии|технический стек|стек технологий|стек|компетенции",
    "education": r"образование|education|курсы|повышение квалификации|сертификаты|сертификация",
    "summary": r"о себе|обо мне|summary|about me|about|профиль|profile|цель|кратко",
    "projects": r"проекты|pet-проекты|pet проекты|projects|портфолио",
    "languages": r"знание языков|языки|languages",
}
_HEAD_RE = {k: re.compile(rf"^\s*(?:{v})\s*[:—-]?\s*$", re.IGNORECASE) for k, v in SECTION_HEADS.items()}

MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8, "сентябр": 9,
          "октябр": 10, "ноябр": 11, "декабр": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MONTH_RE = r"(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]\w*|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*|jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
_DATE = rf"(?:(?P<{{p}}m>{_MONTH_RE})\s+(?P<{{p}}y>(?:19|20)\d\d)|(?P<{{p}}mm>0?[1-9]|1[0-2])[./](?P<{{p}}yy>(?:19|20)\d\d)|(?P<{{p}}yo>(?:19|20)\d\d))"
_NOW = r"(?P<now>настоящее время|по настоящее|н\.\s?в\.|сейчас|по сей день|present|now|current|текущ\w* время)"
RANGE_RE = re.compile(_DATE.format(p="s") + r"\s*(?:[—–\-−]+|по|to|until)\s*(?:" + _DATE.format(p="e") + "|" + _NOW + ")",
                      re.IGNORECASE)
HH_TOTAL_RE = re.compile(r"опыт работы\s*[—\-:–]?\s*(\d{1,2})\s*(?:года|год|лет)(?:\s*(\d{1,2})\s*месяц)?|"
                         r"опыт работы\s*[—\-:–]?\s*(\d{1,2})\s*месяц", re.IGNORECASE)
EDUCATION_LINE = re.compile(r"университет|институт|академи|колледж|лицей|школ|бакалавр|магистр|специалитет|факультет|"
                            r"university|college|bachelor|master|курс[ыа]?\b", re.IGNORECASE)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?\d[\s\-()]*){10,14}")
LINKS = {
    "Telegram": re.compile(r"t\.me/|telegram|телеграм|@[a-z0-9_]{5,}", re.IGNORECASE),
    "LinkedIn": re.compile(r"linkedin\.com|linkedin", re.IGNORECASE),
    "GitHub": re.compile(r"github\.com/[\w-]+|gitlab\.com/[\w-]+", re.IGNORECASE),
    "Портфолио": re.compile(r"behance\.net|dribbble\.com|portfolio|портфолио|kaggle\.com|habr\.com/ru/users", re.IGNORECASE),
}

STRONG_VERBS = re.compile(
    r"\b(разработал|реализовал|внедрил|спроектировал|оптимизировал|ускорил|сократил|снизил|увеличил|автоматизировал|"
    r"создал|запустил|перевел|перевёл|мигрировал|настроил|построил|улучшил|повысил|интегрировал|возглавил|наставлял|"
    r"организовал|покрыл|переписал|сэкономил|вывел|обучил|добился|built|developed|implemented|designed|reduced|"
    r"increased|improved|launched|migrated|automated|led|optimized|created)\w*", re.IGNORECASE)
WEAK_START = re.compile(
    r"^[\s•·\-–—*]*(занимал(ся|ась)|участвовал[аи]?|отвечал[аи]? за|в обязанности входило|обязанности|помогал[аи]?|"
    r"выполнял[аи]?|работа с|работал[аи]? с|осуществлял[аи]?|ведение|поддержка|разработка|написание|тестирование|"
    r"responsible for|worked on|involved in|helped)\b", re.IGNORECASE)
NUMBER_RE = re.compile(
    r"\d+[\d\s.,]*\s*(%|процент|раз\b|x\b|×|мс\b|ms\b|сек|rps|rpm|k\b|к\b|тыс|млн|млрд|пользовател|клиент|заказ|"
    r"запрос|₸|тенге|\$|руб|₽|usd|человек|сотрудник|разработчик|сервис|микросервис|час|дн[еяй]|недел|месяц|строк|тест|"
    r"транзакц|users|customers|requests|hours|days)|\bв\s*\d+[.,]?\d*\s*раз|[x×]\s?\d|[+\-−]\s?\d+\s*%", re.IGNORECASE)
CLICHES = ("стрессоустойчив", "коммуникабел", "ответственн", "быстро обуча", "быстрообуча", "целеустремл", "исполнител",
           "пунктуальн", "командный игрок", "умение работать в команде", "нацелен на результат", "креативн",
           "многозадачн", "активная жизненная позиция", "без вредных привычек", "трудолюб")
PERSONAL = re.compile(r"дата рождения|родил(ся|ась)|возраст|"
                      r"семейное положение|женат|замужем|холост|не замужем|дети\b|есть дети|национальност|вероисповед|"
                      r"паспорт|\bиин\b|\b\d{12}\b", re.IGNORECASE)
ENGLISH_RE = re.compile(r"английск|english|\b(a1|a2|b1|b2|c1|c2)\b|intermediate|upper|advanced|fluent", re.IGNORECASE)


@dataclass
class Parsed:
    text: str
    lines: list[str]
    sections: dict[str, list[str]]  # section key → its lines
    words: int
    contacts: list[str]
    months: int | None
    achievement_lines: list[str]
    skills: list[str]
    head: str  # the first lines: name and the desired position


def _sections(lines: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
    for line in lines:
        if len(line) <= 40:
            key = next((k for k, rx in _HEAD_RE.items() if rx.match(line)), None)
            if key:
                current = key
                out.setdefault(key, [])
                continue
        if current:
            out[current].append(line)
    return out


def _month_of(match: re.Match, p: str) -> tuple[int, int] | None:
    g = match.groupdict()
    if g.get(p + "y"):
        name = g[p + "m"].lower()
        month = next((v for k, v in MONTHS.items() if name.startswith(k)), 6)
        return int(g[p + "y"]), month
    if g.get(p + "yy"):
        return int(g[p + "yy"]), int(g[p + "mm"])
    if g.get(p + "yo"):
        return int(g[p + "yo"]), 7  # only a year: the middle of it
    return None


def experience_months(text: str, experience_lines: list[str] | None = None) -> int | None:
    """Total commercial experience. hh exports state it («Опыт работы — 3 года 5 месяцев»); otherwise the date
    ranges of the experience section are merged (overlapping jobs counted once, education lines ignored)."""
    m = HH_TOTAL_RE.search(text)
    if m:
        if m.group(3):
            return int(m.group(3))
        return int(m.group(1)) * 12 + int(m.group(2) or 0)
    source = experience_lines if experience_lines else [ln for ln in text.split("\n") if not EDUCATION_LINE.search(ln)]
    today = date.today()
    spans = []
    for line in source:
        for r in RANGE_RE.finditer(line):
            start = _month_of(r, "s")
            end = (today.year, today.month) if r.group("now") else _month_of(r, "e")
            if not start or not end:
                continue
            a, b = start[0] * 12 + start[1], end[0] * 12 + end[1]
            if 0 <= b - a <= 12 * 45 and start[0] >= 1970:
                spans.append((a, b))
    if not spans:
        return None
    spans.sort()
    total, cur_a, cur_b = 0, *spans[0]
    for a, b in spans[1:]:
        if a <= cur_b:
            cur_b = max(cur_b, b)
        else:
            total += cur_b - cur_a
            cur_a, cur_b = a, b
    return total + cur_b - cur_a


def parse(text: str) -> Parsed:
    lines = [ln for ln in text.split("\n") if ln.strip()]
    sections = _sections(lines)
    contacts = []
    if EMAIL_RE.search(text):
        contacts.append("Email")
    if any(len(re.sub(r"\D", "", m.group())) >= 10 for m in PHONE_RE.finditer(text)):
        contacts.append("Телефон")
    contacts += [name for name, rx in LINKS.items() if rx.search(text)]
    exp_lines = sections.get("experience") or sections.get("projects") or []
    pool = exp_lines or lines
    achievement = [ln.strip(" •·-–—*") for ln in pool
                   if len(ln.split()) >= 5 and len(ln) <= 400 and not RANGE_RE.search(ln) and not EMAIL_RE.search(ln)]
    return Parsed(
        text=text, lines=lines, sections=sections, words=len(re.findall(r"\w+", text)), contacts=contacts,
        months=experience_months(text, sections.get("experience")), achievement_lines=achievement,
        skills=skills.find_in(text), head="\n".join(lines[:6]),
    )


# ---------- checks ----------
@dataclass
class Context:
    role: str
    grade: Grade
    profile: RoleProfile | None
    market: Market | None


def _years(months: int) -> str:
    y, m = divmod(months, 12)
    parts = []
    if y:
        parts.append(f"{y} " + ("год" if y % 10 == 1 and y % 100 != 11 else "года" if 2 <= y % 10 <= 4 and not 12 <= y % 100 <= 14 else "лет"))
    if m:
        parts.append(f"{m} мес.")
    return " ".join(parts) or "меньше месяца"


def _check(id_, group, title, status, detail, fix="", weight=1) -> Check:
    return Check(id=id_, group=group, title=title, status=status, detail=detail, fix="" if status == P else fix, weight=weight)


def check_contacts(p: Parsed, ctx: Context) -> Check:
    base = [c for c in p.contacts if c in ("Email", "Телефон")]
    extra = [c for c in p.contacts if c in ("Telegram", "LinkedIn")]
    found = ", ".join(p.contacts) or "ничего"
    if not base:
        return _check("contacts", "Структура", "Контакты", F, f"Найдено: {found}. Нет ни почты, ни телефона",
                      "Добавьте в шапку email и телефон, по которым вам удобно ответить", 2)
    if len(base) < 2 and not extra:
        return _check("contacts", "Структура", "Контакты", W, f"Найдено: {found}",
                      "Добавьте второй способ связи: телефон или почту, плюс Telegram. Рекрутеры часто пишут в мессенджер", 2)
    return _check("contacts", "Структура", "Контакты", P, f"Найдено: {found}", weight=2)


def check_length(p: Parsed, ctx: Context) -> Check:
    lo, hi = GRADES[ctx.grade].words
    detail = f"{p.words} слов, для {GRADE_LABELS[ctx.grade]} удобно {lo}–{hi}"
    if p.words < lo * 0.6:
        return _check("length", "Структура", "Объём", F, detail,
                      "Резюме слишком короткое: опишите задачи и результаты на каждом месте работы или в проектах")
    if p.words < lo:
        return _check("length", "Структура", "Объём", W, detail, "Добавьте 2–4 пункта с результатами к последним местам работы")
    if p.words > hi * 1.4:
        return _check("length", "Структура", "Объём", W, detail,
                      "Сократите: оставьте последние 3–4 места работы подробно, старое и нерелевантное — одной строкой")
    return _check("length", "Структура", "Объём", P, detail)


def check_sections(p: Parsed, ctx: Context) -> Check:
    junior = grade_order(ctx.grade) <= grade_order(Grade.junior)
    has = set(p.sections)
    need = ["skills", "education" if junior else "summary"]
    names = {"experience": "опыт работы", "projects": "проекты", "skills": "навыки", "education": "образование", "summary": "о себе"}
    missing = [names[k] for k in need if k not in has]
    found = ", ".join(names[k] for k in names if k in has) or "заголовков разделов не найдено"
    if "experience" not in has and not ("projects" in has and junior):
        return _check("sections", "Структура", "Разделы", F, f"Найдены: {found}",
                      "Выделите раздел «Опыт работы»" + (" или «Проекты» с учебными и pet-проектами" if junior else ""), 2)
    if missing:
        return _check("sections", "Структура", "Разделы", W, f"Найдены: {found}",
                      "Добавьте раздел: " + ", ".join(f"«{m.capitalize()}»" for m in missing), 2)
    return _check("sections", "Структура", "Разделы", P, f"Найдены: {found}", weight=2)


def check_title(p: Parsed, ctx: Context) -> Check:
    head = norm(p.head)
    words = [w for w in norm(ctx.role).replace("-", " ").split() if len(w) > 3]
    keywords = list(ctx.profile.keywords + ctx.profile.hints) if ctx.profile else []
    hit = any(w[:6] in head for w in words) or any(k in head for k in keywords if len(k) > 3)
    if hit:
        return _check("title", "Структура", "Желаемая должность в шапке", P, "Должность видна в начале резюме")
    return _check("title", "Структура", "Желаемая должность в шапке", W, "В первых строках не видно, на какую роль вы претендуете",
                  f"Напишите под именем: «{ctx.role}». По этой строке рекрутер и поиск hh понимают, кто вы")


def check_numbers(p: Parsed, ctx: Context) -> Check:
    lines = p.achievement_lines
    if len(lines) < 3:
        return _check("numbers", "Содержание", "Достижения в цифрах", W, "Опыт описан слишком коротко, чтобы оценить",
                      "Опишите 3–5 результатов на каждом месте: что сделали и что это дало, в цифрах", 3)
    with_num = [ln for ln in lines if NUMBER_RE.search(ln)]
    share = round(len(with_num) * 100 / len(lines))
    detail = f"Цифры есть в {len(with_num)} из {len(lines)} пунктов опыта ({share}%)"
    fix = ("Добавьте измеримый результат к каждому второму пункту: на сколько % ускорили, сколько пользователей, "
           "сколько часов сэкономили, за какой срок сделали")
    if share >= 30:
        return _check("numbers", "Содержание", "Достижения в цифрах", P, detail, weight=3)
    return _check("numbers", "Содержание", "Достижения в цифрах", W if share >= 10 else F, detail, fix, 3)


def check_verbs(p: Parsed, ctx: Context) -> Check:
    weak = [ln for ln in p.achievement_lines if WEAK_START.match(ln)]
    strong = sum(1 for ln in p.achievement_lines if STRONG_VERBS.search(ln))
    detail = f"Пунктов-обязанностей: {len(weak)}, пунктов-результатов: {strong}"
    fix = ("Начинайте пункты с глагола результата: «разработал», «внедрил», «ускорил», «автоматизировал». "
           "«Занимался» и «участвовал» описывают процесс, а не вклад")
    if weak and len(weak) >= strong:
        return _check("verbs", "Содержание", "Результаты, а не обязанности", F, detail, fix, 2)
    if weak or strong < 3:
        return _check("verbs", "Содержание", "Результаты, а не обязанности", W, detail, fix, 2)
    return _check("verbs", "Содержание", "Результаты, а не обязанности", P, detail, weight=2)


def check_cliches(p: Parsed, ctx: Context) -> Check:
    low = p.text.lower().replace("ё", "е")
    found = [c for c in CLICHES if c in low]
    detail = ("Найдено: " + ", ".join(found)) if found else "Общих фраз не найдено"
    fix = "Уберите общие качества или замените фактом: вместо «быстро обучаюсь» — «за 2 месяца освоил Go и перевёл на него сервис»"
    if len(found) >= 3:
        return _check("cliches", "Содержание", "Без шаблонных фраз", F, detail, fix)
    if found:
        return _check("cliches", "Содержание", "Без шаблонных фраз", W, detail, fix)
    return _check("cliches", "Содержание", "Без шаблонных фраз", P, detail)


def check_portfolio(p: Parsed, ctx: Context) -> Check | None:
    if ctx.profile and not ctx.profile.wants_portfolio:
        return None
    junior = grade_order(ctx.grade) <= grade_order(Grade.junior)
    has = [c for c in p.contacts if c in ("GitHub", "Портфолио")]
    if has:
        return _check("portfolio", "Содержание", "Код или портфолио", P, "Есть ссылка: " + ", ".join(has), weight=2 if junior else 1)
    return _check("portfolio", "Содержание", "Код или портфолио", F if junior else W, "Ссылок на GitHub или портфолио нет",
                  "Добавьте ссылку на GitHub или портфолио с 1–2 проектами и README" + (
                      ": для начинающих это главный способ показать уровень" if junior else ""), 2 if junior else 1)


def check_personal(p: Parsed, ctx: Context) -> Check:
    found = sorted({m.group(0).strip().lower() for m in PERSONAL.finditer(p.text)})
    if found:
        return _check("personal", "Содержание", "Лишние личные данные", W, "Найдено: " + ", ".join(found[:5]),
                      "Уберите дату рождения, семейное положение, номер паспорта или ИИН: работодателю они не нужны на "
                      "этапе отклика, а резюме видят многие")
    return _check("personal", "Содержание", "Лишние личные данные", P, "Лишних личных данных не найдено")


def check_english(p: Parsed, ctx: Context) -> Check | None:
    if grade_order(ctx.grade) < grade_order(Grade.middle):
        return None
    if ENGLISH_RE.search(p.text):
        return _check("english", "Содержание", "Уровень английского", P, "Уровень английского указан")
    return _check("english", "Содержание", "Уровень английского", W, "Английский не упомянут",
                  "Укажите уровень английского (например, B1 — читаю документацию). Для middle и выше его спрашивают почти всегда")


def check_experience(p: Parsed, ctx: Context) -> Check:
    lo, hi = GRADES[ctx.grade].months
    label = GRADE_LABELS[ctx.grade]
    want = f"от {_years(lo)}" if hi is None else f"{_years(lo) if lo else '0'} – {_years(hi)}"
    if p.months is None:
        return _check("experience", "Роль и грейд", "Стаж для грейда", W, "Не удалось посчитать стаж: не найдены даты работы",
                      "Укажите месяц и год начала и окончания на каждом месте работы: «март 2022 — настоящее время»", 3)
    detail = f"Стаж по датам: {_years(p.months)}, для {label} обычно {want}"
    if p.months < lo * 0.75:
        return _check("experience", "Роль и грейд", "Стаж для грейда", F, detail,
                      f"Стажа мало для {label}. Либо откликайтесь на грейд ниже, либо сильнее покажите сложность задач: "
                      "архитектурные решения, ответственность, масштаб", 3)
    if p.months < lo:
        return _check("experience", "Роль и грейд", "Стаж для грейда", W, detail,
                      "Стаж на границе: компенсируйте результатами в цифрах и сложными задачами в описании", 3)
    if hi is not None and p.months > hi * 1.5:
        return _check("experience", "Роль и грейд", "Стаж для грейда", W, detail,
                      "Опыта больше, чем обычно у этого грейда: проверьте, не стоит ли претендовать на грейд выше", 3)
    return _check("experience", "Роль и грейд", "Стаж для грейда", P, detail, weight=3)


def check_signals(p: Parsed, ctx: Context) -> Check:
    low = p.text.lower().replace("ё", "е")
    signals = GRADES[ctx.grade].signals
    found = [s for s in signals if re.search(rf"(?<![\w@.]){re.escape(s)}", low)]  # word starts only: not «pet» in an e-mail
    label = GRADE_LABELS[ctx.grade]
    examples = {
        Grade.intern: "учебные и pet-проекты, стажировки, курсы, ссылки на код",
        Grade.junior: "проекты, которые вы сделали сами, и что именно в них реализовали",
        Grade.middle: "самостоятельные задачи от начала до продакшена, оптимизацию, тесты, интеграции",
        Grade.senior: "архитектурные решения, менторство, code review, работу с нагрузкой и техническими решениями",
        Grade.lead: "руководство командой, найм, процессы, планирование и зону ответственности",
    }[ctx.grade]
    detail = f"Найдено признаков: {len(found)}" + (f" ({', '.join(found[:6])})" if found else "")
    fix = f"Покажите то, чего ждут от {label}: {examples}"
    if len(found) >= 3:
        return _check("signals", "Роль и грейд", f"Задачи уровня {label}", P, detail, weight=2)
    return _check("signals", "Роль и грейд", f"Задачи уровня {label}", W if found else F, detail, fix, 2)


def check_role(p: Parsed, ctx: Context) -> Check | None:
    if not ctx.profile:
        return None
    reqs = [r for r in ctx.profile.requirements if grade_order(r.from_grade) <= grade_order(ctx.grade)]
    if not reqs:
        return None
    have = [r for r in reqs if any(skills.covers(p.text, s) for s in r.any_of)]
    missing = [r for r in reqs if r not in have]
    share = round(len(have) * 100 / len(reqs))
    title = f"Базовые навыки: {ctx.profile.label}"
    detail = f"Есть {len(have)} из {len(reqs)}" + (f". Не найдено: {', '.join(r.title for r in missing)}" if missing else "")
    fix = ("Если владеете — впишите в навыки и в описание опыта: " + ", ".join(
        f"{r.title} ({' / '.join(r.any_of[:3])})" for r in missing[:5]) + ". Если нет — это первое, что стоит подтянуть")
    if share >= 80:
        return _check("role", "Роль и грейд", title, P, detail, fix if missing else "", 3)
    return _check("role", "Роль и грейд", title, W if share >= 50 else F, detail, fix, 3)


def check_market(p: Parsed, ctx: Context) -> Check | None:
    m = ctx.market
    if not m or not m.skills:
        return None
    missing = [s for s in m.skills if not s.have and s.share >= 20][:6]
    detail = f"Покрыто {m.coverage}% самых частых требований из {m.sample_size} вакансий"
    fix = ("Если владеете — добавьте в резюме: " + ", ".join(f"{s.name} ({s.share}% вакансий)" for s in missing)) if missing else ""
    if m.coverage >= 60:
        return _check("market", "Рынок", "Совпадение с вакансиями", P, detail, fix, 3)
    return _check("market", "Рынок", "Совпадение с вакансиями", W if m.coverage >= 35 else F, detail, fix, 3)


CHECKS = (check_contacts, check_length, check_sections, check_title, check_numbers, check_verbs, check_cliches,
          check_portfolio, check_personal, check_english, check_experience, check_signals, check_role, check_market)


def run_checks(p: Parsed, ctx: Context) -> list[Check]:
    return [c for fn in CHECKS if (c := fn(p, ctx)) is not None]


def score(checks: list[Check]) -> int:
    total = sum(c.weight for c in checks)
    got = sum(c.weight * {P: 1.0, W: 0.5, F: 0.0}[c.status] for c in checks)
    return round(got * 100 / total) if total else 0


def verdict(value: int, grade: Grade) -> str:
    label = GRADE_LABELS[grade]
    if value >= 80:
        return f"Сильное резюме для {label}: осталось отшлифовать детали"
    if value >= 60:
        return "Хорошая основа, но несколько вещей мешают резюме продавать вас"
    if value >= 40:
        return "Резюме нужно доработать: сейчас рекрутер может пролистать его"
    return "Резюме пока слабо показывает ваш уровень: начните с первых рекомендаций"


# ---------- templates for weak lines ----------
_VERB_BY_TOPIC = [
    (re.compile(r"тест", re.I), "Покрыл(а) тестами"),
    (re.compile(r"оптимиз|ускор|производительн|быстр", re.I), "Ускорил(а)"),
    (re.compile(r"автоматиз", re.I), "Автоматизировал(а)"),
    (re.compile(r"интеграц|интегр", re.I), "Интегрировал(а)"),
    (re.compile(r"внедр|настро", re.I), "Внедрил(а)"),
    (re.compile(r"поддерж|сопровожд|исправл|баг", re.I), "Стабилизировал(а)"),
    (re.compile(r"миграц|перевод|переход", re.I), "Перевёл(а)"),
    (re.compile(r"команд|руковод|управл", re.I), "Руководил(а)"),
    (re.compile(r"анализ|отчет|отчёт|дашборд", re.I), "Построил(а)"),
]


def rewrite_templates(p: Parsed, limit: int = 5) -> list[Rewrite]:
    """Weak lines (duties, no numbers) with a template of a stronger line. Russian grammar is too irregular to rewrite
    the sentence itself reliably, so the template keeps the facts as placeholders for you to fill in."""
    out = []
    for line in p.achievement_lines:
        weak = bool(WEAK_START.match(line))
        no_number = not NUMBER_RE.search(line)
        if not (weak or no_number) or len(line) < 25:
            continue
        verb = next((v for rx, v in _VERB_BY_TOPIC if rx.search(line)), "Разработал(а)")
        techs = skills.find_in(line)
        how = f" на {', '.join(techs[:3])}" if techs else ""
        after = f"{verb} [что именно]{how}, что [дало результат: на сколько % быстрее / сколько пользователей / сколько часов в неделю сэкономлено]"
        why = ("Пункт описывает обязанность, а не результат" if weak else "Нет цифры, по которой видно масштаб") + (
            ". Начните с глагола результата и закончите эффектом" if weak else ". Добавьте измеримый эффект")
        out.append(Rewrite(before=line, after=after, why=why))
        if len(out) >= limit:
            break
    return out


# ---------- summary ----------
def strengths_and_weaknesses(checks: list[Check], p: Parsed, market: Market | None) -> tuple[list[str], list[str]]:
    strengths = [f"{c.title}: {c.detail}" for c in checks if c.status == P and c.weight >= 2]
    if market:
        top = [s for s in market.skills if s.have][:4]
        if top:
            strengths.append("Есть востребованные навыки: " + ", ".join(f"{s.name} ({s.share}% вакансий)" for s in top))
    weaknesses = [f"{c.title}: {c.detail}" for c in sorted(checks, key=lambda c: -c.weight) if c.status == F]
    weaknesses += [f"{c.title}: {c.detail}" for c in sorted(checks, key=lambda c: -c.weight) if c.status == W and c.weight >= 2]
    return strengths[:6], weaknesses[:6]


def recommendations(checks: list[Check], ctx: Context) -> list[Recommendation]:
    recs: list[Recommendation] = []
    for c in sorted(checks, key=lambda c: (c.status != F, -c.weight)):
        if c.status == P and not c.fix:
            continue
        priority = 1 if c.status == F and c.weight >= 2 else 2 if c.status != P and (c.status == F or c.weight >= 2) else 3
        recs.append(Recommendation(priority=priority, title=c.title, detail=c.fix))
    # growth: what the next grade will ask for
    if ctx.profile and ctx.grade != Grade.lead:
        nxt = list(Grade)[grade_order(ctx.grade) + 1]
        future = [r for r in ctx.profile.requirements if r.from_grade == nxt]
        if future:
            recs.append(Recommendation(
                priority=3, title=f"На вырост: чего ждут от {GRADE_LABELS[nxt]}",
                detail="Когда закроете текущие пункты, подтяните и покажите в резюме: " + ", ".join(
                    f"{r.title} ({' / '.join(r.any_of[:3])})" for r in future)))
    recs.sort(key=lambda r: r.priority)
    return recs[:10]


def facts(p: Parsed) -> ResumeFacts:
    return ResumeFacts(words=p.words, experience_months=p.months, contacts=p.contacts, skills_found=p.skills)


def build_context(role: str, grade: Grade, market: Market | None) -> Context:
    return Context(role=role, grade=grade, profile=match_role(role), market=market)
