"""Request and response bodies of the HTTP API. The frontend types are generated from these (OpenAPI)."""
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kolenke.schemas.enums import ChatStatus, CompanyStatus, Stage, VacancyStatus


class ApiModel(BaseModel):
    """In responses every field is always present, so the OpenAPI schema marks fields with defaults as required
    there; in request bodies they stay optional."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Ok(ApiModel):
    ok: bool = True


class Ids(ApiModel):
    ids: list[int] = Field(min_length=1, max_length=5000)


# ---------- vacancies ----------
class Reason(ApiModel):
    ok: bool
    text: str


class Contacts(ApiModel):
    emails: list[str] = []
    phones: list[str] = []
    telegram: list[str] = []
    person: str = ""


class Vacancy(ApiModel):
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)

    id: int
    source: str
    ext_id: str | None = None
    url: str
    title: str | None = None
    company: str | None = None
    status: VacancyStatus
    note: str | None = None
    created_at: str | None = None
    applied_at: str | None = None
    resume: str | None = None
    hh_state: str | None = None
    hh_state_at: str | None = None
    letter_sent: int | None = None
    salary_text: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    experience: str | None = None
    skill_match: int | None = None
    invited_at: str | None = None
    reviewed_at: str | None = None
    stage: Stage | None = None
    next_step: str | None = None
    next_at: str | None = None
    followup: str | None = None
    location: str | None = None
    country: str | None = None
    remote: int | None = None
    summary: str | None = None
    company_url: str | None = None
    skills: str | None = None
    contacts: Contacts | None = None  # found on other sites: e-mails, phones, Telegram, contact person

    @field_validator("contacts", mode="before")
    @classmethod
    def _parse_contacts(cls, v):
        return json.loads(v) if isinstance(v, str) and v else v or None


class VacancyEvent(ApiModel):
    ts: str
    kind: str
    text: str


class FormAnswer(ApiModel):
    q: str
    a: str


class ChatItem(ApiModel):
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)

    id: int
    chat_id: str | None = None
    msg_id: str | None = None
    company: str | None = None
    vacancy: str | None = None
    message: str | None = None
    reply: str | None = None
    robot: int | None = None
    status: ChatStatus
    created_at: str | None = None
    sent_at: str | None = None


class VacancyDetail(Vacancy):
    letter: str | None = None
    notes: str | None = None
    stage_manual: int | None = None
    stage_at: str | None = None
    followup_text: str | None = None
    match_info: list[Reason] = []
    form_answers: list[FormAnswer] = []
    events: list[VacancyEvent] = []
    chats: list[ChatItem] = []


class VacancyAdd(ApiModel):
    url: str = Field(pattern=r"^https?://", max_length=2000)
    title: str = ""
    company: str = ""
    source: str = "other"


class StatusChange(Ids):
    status: VacancyStatus
    review: bool = False  # the change was made in the review (swipe) screen


class QueueNew(ApiModel):
    source: str = "hh"


class Count(ApiModel):
    count: int


class ToCompaniesResult(ApiModel):
    added: int
    no_email: int


# ---------- pipeline ----------
class StageInfo(ApiModel):
    id: Stage
    label: str


class PipelineCard(ApiModel):
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)

    id: int
    source: str
    url: str
    title: str | None = None
    company: str | None = None
    stage: Stage | None = None
    stage_manual: int | None = None
    stage_at: str | None = None
    notes: str | None = None
    next_step: str | None = None
    next_at: str | None = None
    hh_state: str | None = None
    applied_at: str | None = None
    created_at: str | None = None
    followup: str | None = None


class Pipeline(ApiModel):
    stages: list[StageInfo]
    cards: list[PipelineCard]


class PipelineUpdate(ApiModel):
    """Only the fields you send are changed."""
    stage: Stage | None = None
    notes: str | None = Field(None, max_length=10000)
    next_step: str | None = Field(None, max_length=200)
    next_at: str | None = None  # local ISO datetime, empty to clear


class PlannedStep(ApiModel):
    id: int
    title: str | None = None
    company: str | None = None
    stage: Stage | None = None
    next_step: str | None = None
    next_at: str


class FollowupCandidate(ApiModel):
    id: int
    title: str | None = None
    company: str | None = None
    url: str
    stage: Stage | None = None
    sent: str | None = None


class Reminders(ApiModel):
    upcoming: list[PlannedStep]
    past: list[PlannedStep]
    followups: list[FollowupCandidate]


class FollowupSend(ApiModel):
    text: str = Field(min_length=1, max_length=4000)


class FollowupClose(ApiModel):
    action: str = Field(pattern="^(done|dismissed)$")


class Draft(ApiModel):
    text: str


class Started(ApiModel):
    ok: bool = True
    started: bool  # False: another task is running, it will be sent by the next one


# ---------- companies ----------
class Company(ApiModel):
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)

    id: int
    name: str | None = None
    email: str
    position: str | None = None
    status: CompanyStatus
    note: str | None = None
    created_at: str | None = None
    sent_at: str | None = None


class CompanyAdd(ApiModel):
    name: str = Field("", max_length=300)
    email: str = Field(max_length=300)
    position: str = Field("", max_length=300)


class CompanyUpdate(ApiModel):
    name: str = Field("", max_length=300)
    position: str = Field("", max_length=300)


class CompanyStatusChange(Ids):
    status: CompanyStatus


class Added(ApiModel):
    ok: bool = True
    added: int


class MailPreview(ApiModel):
    to: str
    subject: str
    body: str
    attachments: list[str]


class MailTest(ApiModel):
    ok: bool
    message: str


# ---------- chats & answers ----------
class ChatReply(ApiModel):
    reply: str = Field(min_length=1, max_length=4000)


class Answer(ApiModel):
    id: int | None = None
    topic: str = Field("", max_length=200)
    keywords: str = Field("", max_length=1000)
    answer: str = Field("", max_length=4000)


class AnswersSave(ApiModel):
    items: list[Answer]


class AnswerMatch(ApiModel):
    topic: str | None
    answer: str


class Question(ApiModel):
    id: int
    text: str
    source: str | None = None
    seen: int
    created_at: str | None = None


# ---------- jobs, status, stats ----------
class TaskInfo(ApiModel):
    key: str
    title: str


class LogLine(ApiModel):
    ts: str
    msg: str


class Week(ApiModel):
    start: str
    invites: int
    applied: int
    applied_all: int
    invites_all: int
    rate: float | None


class Status(ApiModel):
    running: bool
    job: str | None
    log: list[LogLine]
    vacancies: dict[str, int]
    companies: dict[str, int]
    applied_today: int
    week: Week
    review: int
    sent_today: int
    chats_pending: int
    attention: int
    reminders: int
    no_letter: int
    autopilot_next: str | None


class DayCount(ApiModel):
    day: str | None
    hh: int
    mail: int


class StateCount(ApiModel):
    state: str
    n: int


class ResumeCount(ApiModel):
    resume: str
    n: int
    invites: int | None
    discards: int | None


class SkipReason(ApiModel):
    note: str | None
    n: int


class Stats(ApiModel):
    by_day: list[DayCount]
    hh_states: list[StateCount]
    by_resume: list[ResumeCount]
    skipped: list[SkipReason]


class SearchVacancy(ApiModel):
    id: int
    source: str
    title: str | None
    company: str | None
    status: VacancyStatus
    created_at: str | None


class SearchChat(ApiModel):
    id: int
    chat_id: str | None
    company: str | None
    vacancy: str | None
    message: str | None
    status: ChatStatus
    created_at: str | None


class SearchCompany(ApiModel):
    id: int
    name: str | None
    email: str
    position: str | None
    status: CompanyStatus


class SearchResult(ApiModel):
    vacancies: list[SearchVacancy]
    chats: list[SearchChat]
    companies: list[SearchCompany]


class ResumeUploaded(ApiModel):
    ok: bool = True
    name: str
