"""Text helpers shared by filters, search and templates."""
import re
from datetime import date, timedelta

from kolenke.schemas.settings import AppSettings


def norm(text: str | None) -> str:
    """Lower case, ё → е, no quotes or brackets, single spaces: for comparing company names and titles."""
    return re.sub(r"\s+", " ", re.sub(r"[«»\"'()]", "", (text or "").lower().replace("ё", "е"))).strip()


def split_list(text: str | None) -> list[str]:
    """«kaspi, halyk\\nforte» → normalized items."""
    return [norm(w) for w in re.split(r"[,\n;]", text or "") if norm(w)]


def fill(template: str, s: AppSettings, company: str | None = "", position: str | None = "") -> str:
    """Letter templates: {name} {phone} {company} {position}; an empty position falls back to the desired one."""
    values = {"name": s.full_name, "phone": s.phone, "company": company or "", "position": position or s.desired_position}
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out


def week_start() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()
