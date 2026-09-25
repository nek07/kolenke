from enum import StrEnum


class VacancySource(StrEnum):
    hh = "hh"
    habr = "habr"
    enbek = "enbek"
    other = "other"


class VacancyStatus(StrEnum):
    new = "new"
    queued = "queued"
    applied = "applied"
    skipped = "skipped"
    attention = "attention"  # the employer questionnaire needs your answers
    error = "error"


class Stage(StrEnum):
    """Pipeline after the response."""
    applied = "applied"
    viewed = "viewed"
    invited = "invited"
    interview = "interview"
    offer = "offer"
    declined = "declined"


STAGE_LABELS = {
    Stage.applied: "Отклик", Stage.viewed: "Просмотрен", Stage.invited: "Приглашение",
    Stage.interview: "Собеседование", Stage.offer: "Оффер", Stage.declined: "Не сейчас",
}


class Followup(StrEnum):
    approved = "approved"
    sent = "sent"
    done = "done"
    dismissed = "dismissed"


class CompanyStatus(StrEnum):
    new = "new"
    queued = "queued"
    sent = "sent"
    error = "error"


class ChatStatus(StrEnum):
    pending = "pending"      # waits for your reply
    info = "info"            # a notice that needs no reply
    approved = "approved"    # your reply, waiting to be sent
    sent = "sent"
    auto_sent = "auto_sent"  # answered from the answer base
    closed = "closed"        # the employer closed the chat
    hidden = "hidden"


class HhMode(StrEnum):
    resume = "resume"  # vacancies hh recommends for a resume
    query = "query"    # text search


class AutopilotMode(StrEnum):
    review = "review"  # find and notify, you swipe
    auto = "auto"      # apply at once


class Experience(StrEnum):
    no_experience = "noExperience"
    between_1_and_3 = "between1And3"
    between_3_and_6 = "between3And6"
    more_than_6 = "moreThan6"


EXPERIENCE_LABELS = {
    Experience.no_experience: "без опыта",
    Experience.between_1_and_3: "1–3 года",
    Experience.between_3_and_6: "3–6 лет",
    Experience.more_than_6: "более 6 лет",
}
