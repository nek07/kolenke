"""Request and response bodies of the HTTP API. The frontend types are generated from these (OpenAPI)."""
from pydantic import BaseModel, ConfigDict, Field

from kolenke.schemas.enums import ChatStatus, CompanyStatus, Stage, VacancyStatus


class Ok(BaseModel):
    ok: bool = True


class Ids(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)


# ---------- vacancies ----------
class Reason(BaseModel):
    ok: bool
    text: str


class Contacts(BaseModel):
    emails: list[str] = []
    phones: list[str] = []
    telegram: list[str] = []
    person: str = ""


class Vacancy(BaseModel):
    model_config = ConfigDict(extra="ignore")

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


class VacancyEvent(BaseModel):
    ts: str
    kind: str
    text: str


class FormAnswer(BaseModel):
    q: str
    a: str


class ChatItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

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
    contacts: Contacts | None = None
    events: list[VacancyEvent] = []
    chats: list[ChatItem] = []


class VacancyAdd(BaseModel):
    url: str = Field(pattern=r"^https?://", max_length=2000)
    title: str = ""
    company: str = ""
    source: str = "other"


class StatusChange(Ids):
    status: VacancyStatus
    review: bool = False  # the change was made in the review (swipe) screen


class QueueNew(BaseModel):
    source: str = "hh"


class Count(BaseModel):
    count: int


class ToCompaniesResult(BaseModel):
    added: int
    no_email: int


# ---------- pipeline ----------
class StageInfo(BaseModel):
    id: Stage
    label: str


class PipelineCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

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


class Pipeline(BaseModel):
    stages: list[StageInfo]
    cards: list[PipelineCard]


class PipelineUpdate(BaseModel):
    """Only the fields you send are changed."""
    stage: Stage | None = None
    notes: str | None = Field(None, max_length=10000)
    next_step: str | None = Field(None, max_length=200)
    next_at: str | None = None  # local ISO datetime, empty to clear


class PlannedStep(BaseModel):
    id: int
    title: str | None = None
    company: str | None = None
    stage: Stage | None = None
    next_step: str | None = None
    next_at: str


class FollowupCandidate(BaseModel):
    id: int
    title: str | None = None
    company: str | None = None
    url: str
    stage: Stage | None = None
    sent: str | None = None


class Reminders(BaseModel):
    upcoming: list[PlannedStep]
    past: list[PlannedStep]
    followups: list[FollowupCandidate]


class FollowupSend(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class FollowupClose(BaseModel):
    action: str = Field(pattern="^(done|dismissed)$")


class Draft(BaseModel):
    text: str


class Started(BaseModel):
    ok: bool = True
    started: bool  # False: another task is running, it will be sent by the next one


# ---------- companies ----------
class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str | None = None
    email: str
    position: str | None = None
    status: CompanyStatus
    note: str | None = None
    created_at: str | None = None
    sent_at: str | None = None


class CompanyAdd(BaseModel):
    name: str = Field("", max_length=300)
    email: str = Field(max_length=300)
    position: str = Field("", max_length=300)


class CompanyUpdate(BaseModel):
    name: str = Field("", max_length=300)
    position: str = Field("", max_length=300)


class CompanyStatusChange(Ids):
    status: CompanyStatus


class Added(BaseModel):
    ok: bool = True
    added: int


class MailPreview(BaseModel):
    to: str
    subject: str
    body: str
    attachments: list[str]


class MailTest(BaseModel):
    ok: bool
    message: str


# ---------- chats & answers ----------
class ChatReply(BaseModel):
    reply: str = Field(min_length=1, max_length=4000)


class Answer(BaseModel):
    id: int | None = None
    topic: str = Field("", max_length=200)
    keywords: str = Field("", max_length=1000)
    answer: str = Field("", max_length=4000)


class AnswersSave(BaseModel):
    items: list[Answer]


class AnswerMatch(BaseModel):
    topic: str | None
    answer: str


class Question(BaseModel):
    id: int
    text: str
    source: str | None = None
    seen: int
    created_at: str | None = None


# ---------- jobs, status, stats ----------
class TaskInfo(BaseModel):
    key: str
    title: str


class LogLine(BaseModel):
    ts: str
    msg: str


class Week(BaseModel):
    start: str
    invites: int
    applied: int
    applied_all: int
    invites_all: int
    rate: float | None


class Status(BaseModel):
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


class DayCount(BaseModel):
    day: str | None
    hh: int
    mail: int


class StateCount(BaseModel):
    state: str
    n: int


class ResumeCount(BaseModel):
    resume: str
    n: int
    invites: int | None
    discards: int | None


class SkipReason(BaseModel):
    note: str | None
    n: int


class Stats(BaseModel):
    by_day: list[DayCount]
    hh_states: list[StateCount]
    by_resume: list[ResumeCount]
    skipped: list[SkipReason]


class SearchVacancy(BaseModel):
    id: int
    source: str
    title: str | None
    company: str | None
    status: VacancyStatus
    created_at: str | None


class SearchChat(BaseModel):
    id: int
    chat_id: str | None
    company: str | None
    vacancy: str | None
    message: str | None
    status: ChatStatus
    created_at: str | None


class SearchCompany(BaseModel):
    id: int
    name: str | None
    email: str
    position: str | None
    status: CompanyStatus


class SearchResult(BaseModel):
    vacancies: list[SearchVacancy]
    chats: list[SearchChat]
    companies: list[SearchCompany]


class ResumeUploaded(BaseModel):
    ok: bool = True
    name: str
