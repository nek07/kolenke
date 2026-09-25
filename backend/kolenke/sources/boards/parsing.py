"""Pure text parsing shared by the boards: contacts, country, currency, salary and summaries."""
import html
import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
TG_RE = re.compile(r"(?:t\.me/|telegram\.me/)([A-Za-z0-9_]{4,32})|(?:telegram|телеграм|tg)\W{0,3}@([A-Za-z0-9_]{4,32})", re.I)
JUNK_EMAIL = re.compile(r"noreply|no-reply|example\.|sentry|@2x|\.(png|jpe?g|svg|gif|webp)$|support@habr|@habr\.|@enbek\.kz$", re.I)


def extract_contacts(text: str | None) -> dict:
    """E-mails, phones and Telegram handles mentioned in free text."""
    text = text or ""
    emails = []
    for e in EMAIL_RE.findall(text):
        e = e.strip(".").lower()
        if not JUNK_EMAIL.search(e) and e not in emails:
            emails.append(e)
    phones = []
    for ph in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", ph)
        digits = "7" + digits[1:] if digits.startswith("8") else digits
        if len(digits) == 11:
            nice = f"+7 {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:]}"
            if nice not in phones:
                phones.append(nice)
    tg = []
    for a, b in TG_RE.findall(text):
        h = "@" + (a or b)
        if h.lower() not in [t.lower() for t in tg]:
            tg.append(h)
    return {"emails": emails, "phones": phones, "telegram": tg}


def merge_contacts(*parts: dict) -> dict:
    out = {"emails": [], "phones": [], "telegram": [], "person": ""}
    for p in parts:
        for k in ("emails", "phones", "telegram"):
            for x in p.get(k) or []:
                if x not in out[k]:
                    out[k].append(x)
        out["person"] = out["person"] or p.get("person") or ""
    return out


KZ_CITIES = ("алматы", "астана", "нур-султан", "шымкент", "караганд", "актобе", "атырау", "актау", "павлодар", "усть-каменогорск",
             "семей", "костанай", "кызылорд", "тараз", "уральск", "петропавловск", "туркестан", "талдыкорган", "кокшетау", "экибастуз")
COUNTRY_BY_CITY = {
    "Россия": ("москва", "санкт-петербург", "новосибирск", "екатеринбург", "казань", "нижний новгород", "самара", "краснодар",
               "ростов", "пермь", "воронеж", "уфа", "челябинск", "омск", "томск", "иннополис", "калининград", "тюмень", "россия"),
    "Беларусь": ("минск", "беларусь"),
    "Узбекистан": ("ташкент", "узбекистан"),
    "Кыргызстан": ("бишкек", "кыргызстан"),
    "Армения": ("ереван",), "Грузия": ("тбилиси",), "Сербия": ("белград",), "Кипр": ("лимасол", "кипр"),
}


def country_of(locations: list[str] | None, remote: bool = False) -> str:
    low = " ".join(locations or []).lower()
    if any(c in low for c in KZ_CITIES) or "казахстан" in low:
        return "Казахстан"
    for country, cities in COUNTRY_BY_CITY.items():
        if any(c in low for c in cities):
            return country
    return "Удалённо" if remote else ""


def currency_of(salary_text: str | None) -> str:
    t = (salary_text or "").lower()
    if "₽" in t or "руб" in t:
        return "RUB"
    if "$" in t or "usd" in t:
        return "USD"
    if "€" in t or "eur" in t:
        return "EUR"
    return "KZT" if ("₸" in t or "тенге" in t or "kzt" in t or re.search(r"\d", t)) else ""


def tidy_salary(text: str | None) -> str | None:
    """Enbek writes a fixed salary as «от 800 000 до 800 000 тенге»."""
    if not text:
        return text
    t = re.sub(r"\s+", " ", text).strip()
    m = re.fullmatch(r"от ([\d ]*\d) до ([\d ]*\d) (\D.*)", t)
    return f"{m.group(1)} {m.group(3)}" if m and m.group(1) == m.group(2) else t


def summarize(text: str | None, limit: int = 280) -> str:
    t = re.sub(r"\s+", " ", html.unescape(text or "")).strip()  # Enbek keeps entities like &middot; in its texts
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"
