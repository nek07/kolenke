"""User settings: one typed model instead of string key-value pairs.

The database keeps every setting as text (the format predates this model), so `from_storage` reads it leniently:
a value that cannot be parsed falls back to the default and numbers are clamped to their bounds. Writes through the
API are strict instead: a wrong value is a 422 for the form to show."""
import json
import re
from enum import Enum
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from annotated_types import Ge, Le
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
from pydantic.fields import FieldInfo

from kolenke.schemas.enums import AutopilotMode, Experience, HhMode

Count = Annotated[int, Ge(1)]
NonNegative = Annotated[int, Ge(0)]


class HhResume(BaseModel):
    hash: str
    title: str


class SettingsFields(BaseModel):
    """Every setting with its default. Shared by the stored model, the page's view and the partial update."""

    # profile
    full_name: str = ""
    phone: str = ""
    desired_position: str = ""
    resume_file: str = ""  # set only by the resume upload

    # hh search
    hh_domain: str = Field("hh.kz", pattern=r"^(hh\.(kz|ru|uz)|rabota\.by)$")
    hh_mode: HhMode = HhMode.resume
    hh_resume_hash: str = ""
    hh_resumes: list[HhResume] = []  # cached list of the user's hh resumes, filled by the bot
    hh_query: str = ""
    hh_area: str = Field("", pattern=r"^\d*$")  # e.g. 160 = Алматы, 159 = Астана; empty = all
    hh_pages: Annotated[int, Ge(1), Le(20)] = 3
    hh_daily_limit: Count = 50  # safety limit against captcha, not a goal
    hh_weekly_goal: Count = 150
    hh_pause_min: NonNegative = 4  # seconds between two responses, random in [min, max]
    hh_pause_max: NonNegative = 9
    hh_exclude: str = ""  # comma-separated words; a vacancy title containing any is skipped
    hh_letter_template: str = (
        "Здравствуйте!\n\nМеня заинтересовала вакансия «{position}» в компании {company}. "
        "Буду рад(а) обсудить, чем могу быть полезен(на) вашей команде.\n\n"
        "С уважением,\n{name}\n{phone}"
    )

    # smart filters
    f_salary_min: NonNegative | None = None  # upper bound of the salary must reach this
    f_skip_no_salary: bool = False
    f_experience: list[Experience] = []
    f_exclude_companies: str = ""  # one per line or comma-separated, part of the name is enough
    f_skip_rejected: bool = True  # don't apply again where you were already refused
    f_min_match: Annotated[int, Ge(0), Le(100)] = 0  # hh skill match, %; vacancies without the mark are kept
    f_sort_match: bool = True  # best skill match first in the review and the apply queue

    # chats
    chat_auto: bool = True  # answer HR robots automatically when the answer base has an answer
    chat_max: Count = 20  # unread chats handled per check
    chat_robot_steps: Count = 10  # robot questions answered in a row in one chat

    # mail
    smtp_host: str = "smtp.gmail.com"
    smtp_port: Annotated[int, Ge(1), Le(65535)] = 465
    smtp_user: str = ""
    smtp_password: str = ""
    mail_daily_limit: Count = 80
    mail_delay_min: NonNegative = 40
    mail_delay_max: NonNegative = 90
    mail_subject_template: str = "Резюме: {name} — {position}"
    mail_body_template: str = (
        "Здравствуйте!\n\nМеня зовут {name}. Хотел(а) бы предложить свою кандидатуру "
        "на позицию «{position}» в {company}. Резюме во вложении.\n\n"
        "Буду благодарен(на) за обратную связь.\n\nС уважением,\n{name}\n{phone}"
    )

    # autopilot
    autopilot_on: bool = False
    autopilot_mode: AutopilotMode = AutopilotMode.review
    autopilot_interval: Count = 30  # minutes
    autopilot_from: Annotated[int, Ge(0), Le(23)] = 8
    autopilot_to: Annotated[int, Ge(1), Le(24)] = 22

    # other sites
    other_query: str = ""  # empty = the hh query or the desired position
    other_sites: list[str] = ["habr", "enbek"]
    other_pages: Annotated[int, Ge(1), Le(10)] = 2
    other_countries: str = ""  # countries and/or cities, e.g. «Казахстан, удалённо»; empty = any
    other_monitor: bool = True  # check other sites in every autopilot cycle
    other_max_details: NonNegative = 40  # vacancy pages opened per check (0 = only the lists)

    # after the response
    followup_days: Count = 5
    followup_template: str = (
        "Здравствуйте! Несколько дней назад я откликнулся(ась) на вакансию «{position}». "
        "Подскажите, пожалуйста, актуальна ли она и удобно ли обсудить мою кандидатуру? "
        "Буду рад(а) ответить на любые вопросы.\n\nС уважением,\n{name}"
    )


class AppSettings(SettingsFields):
    @property
    def resume_title(self) -> str:
        return next((r.title for r in self.hh_resumes if r.hash == self.hh_resume_hash), "")

    @classmethod
    def from_storage(cls, raw: dict[str, str]) -> "AppSettings":
        values: dict[str, Any] = {}
        for name, field in cls.model_fields.items():
            if name not in raw:
                continue
            try:
                value = _clamp(field.metadata, _parse(field.annotation, raw[name]))
                values[name] = getattr(cls.model_validate({name: value}), name)
            except (ValueError, TypeError, ValidationError):
                pass  # unreadable stored value: keep the default
        return cls.model_validate(values)

    def to_storage(self, names: set[str] | None = None) -> dict[str, str]:
        dumped = self.model_dump(mode="json")
        return {k: _serialize(v) for k, v in dumped.items() if names is None or k in names}


# PATCH body: every editable field becomes optional, only the ones sent are applied.
# The bot-owned fields are left out; an empty smtp_password keeps the stored one.
_BOT_OWNED = {"resume_file", "hh_resumes"}
SettingsUpdate = create_model(
    "SettingsUpdate",
    __config__=ConfigDict(extra="ignore"),
    **{
        name: (f.annotation | None, FieldInfo.merge_field_infos(f, default=None))
        for name, f in SettingsFields.model_fields.items()
        if name not in _BOT_OWNED
    },
)


class SettingsOut(SettingsFields):
    """What the page sees: the password itself never leaves the server."""
    smtp_password: str = Field("", exclude=True)
    has_password: bool = False
    resume_name: str = ""


def _unwrap(annotation) -> tuple[type, bool]:
    """(base type, optional) of a field annotation, e.g. `NonNegative | None` → (int, True)."""
    optional = False
    if get_origin(annotation) in (Union, UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        optional, annotation = len(args) < len(get_args(annotation)), args[0]
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return (get_origin(annotation) or annotation), optional


def _parse(annotation, raw: str | None):
    text = "" if raw is None else str(raw)
    kind, optional = _unwrap(annotation)
    if kind is bool:
        return text.strip().lower() in ("1", "true", "yes", "on")
    if kind is int and optional:
        digits = re.sub(r"\D", "", text)  # «400 000» → 400000, empty → not set
        return int(digits) if digits else None
    if kind is int:
        return int(float(text.replace(",", ".").strip()))
    if kind is list:
        items = json.loads(text) if text.strip().startswith("[") else [p.strip() for p in text.split(",") if p.strip()]
        item_type = (get_args(_unwrap_annotated(annotation)) or (str,))[0]
        if isinstance(item_type, type) and issubclass(item_type, Enum):
            items = [i for i in items if i in item_type._value2member_map_]  # an unknown code must not drop the rest
        return items
    return text


def _unwrap_annotated(annotation):
    return get_args(annotation)[0] if get_origin(annotation) is Annotated else annotation


def _clamp(metadata, value):
    if not isinstance(value, int) or isinstance(value, bool):
        return value
    for m in metadata:
        if isinstance(m, Ge):
            value = max(m.ge, value)
        if isinstance(m, Le):
            value = min(m.le, value)
    return value


def _serialize(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return json.dumps(value, ensure_ascii=False)
        return ",".join(str(v) for v in value)
    return str(value)
