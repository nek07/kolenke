"""Resume review: the report the page shows, the history list and the market sample behind it."""
from kolenke.schemas.api import ApiModel
from kolenke.schemas.enums import CheckStatus, Grade, ReviewStatus


class Check(ApiModel):
    """One test the resume went through, e.g. «Достижения в цифрах»."""
    id: str
    group: str  # Структура, Содержание, Роль и грейд, Рынок
    title: str
    status: CheckStatus
    detail: str  # what was found
    fix: str = ""  # what to do, empty when passed
    weight: int = 1


class MarketSkill(ApiModel):
    name: str
    share: int  # % of the sampled vacancies that ask for it
    have: bool  # found in the resume


class MarketVacancyRef(ApiModel):
    title: str
    company: str = ""
    url: str
    source: str


class Salary(ApiModel):
    currency: str
    low: int  # 25th percentile of the sample
    median: int
    high: int  # 75th percentile
    count: int


class Market(ApiModel):
    query: str
    sample_size: int
    sources: list[str] = []
    note: str = ""  # e.g. «hh показал капчу, взял 12 вакансий из 25»
    skills: list[MarketSkill] = []
    coverage: int = 0  # % of the top skills (weighted by share) found in the resume
    salary: Salary | None = None
    title_words: list[str] = []  # words employers put in titles: «Python», «Backend», «FastAPI»
    examples: list[MarketVacancyRef] = []


class Recommendation(ApiModel):
    priority: int  # 1 = do it first
    title: str
    detail: str


class Rewrite(ApiModel):
    before: str
    after: str
    why: str
    by_ai: bool = False


class AiPart(ApiModel):
    used: bool = False
    model: str = ""
    summary: str = ""
    grade_fit: str = ""  # «соответствует», «ниже», «выше»
    grade_comment: str = ""
    error: str = ""


class Diff(ApiModel):
    """Compared with the previous review of the same role and grade: what you already improved."""
    previous_id: int
    previous_score: int
    score_delta: int
    fixed: list[str] = []
    new_issues: list[str] = []
    skills_added: list[str] = []
    same_resume: bool = False  # the text did not change: the difference comes from the market


class ResumeFacts(ApiModel):
    words: int
    experience_months: int | None = None  # estimated from the dates in the resume
    contacts: list[str] = []  # email, телефон, Telegram, GitHub...
    skills_found: list[str] = []


class ResumeReport(ApiModel):
    score: int
    verdict: str
    role: str
    role_profile: str = ""  # the built-in profile the role matched, e.g. «Backend-разработчик»
    grade: Grade
    facts: ResumeFacts
    checks: list[Check]
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[Recommendation]
    rewrites: list[Rewrite]
    market: Market | None = None
    ai: AiPart = AiPart()
    diff: Diff | None = None


class ReviewSummary(ApiModel):
    id: int
    created_at: str
    finished_at: str | None = None
    status: ReviewStatus
    progress: str | None = None
    role: str
    grade: Grade
    source_name: str
    use_market: bool
    use_ai: bool
    score: int | None = None
    error: str | None = None


class ReviewDetail(ReviewSummary):
    report: ResumeReport | None = None


class RoleOption(ApiModel):
    key: str
    label: str


class AiStatus(ApiModel):
    running: bool
    model_ready: bool
    models: list[str] = []
    message: str


class ReviewOptions(ApiModel):
    roles: list[RoleOption]
    grades: list[RoleOption]
    ai_available: bool  # AI review switched on in the settings
