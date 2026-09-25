from fastapi import APIRouter, HTTPException

from kolenke.db.repositories import answers, chats
from kolenke.schemas.api import Answer, AnswerMatch, AnswersSave, ChatItem, ChatReply, Ok, Question, Started
from kolenke.schemas.enums import ChatStatus
from kolenke.services import answers as answers_service
from kolenke.workers.runner import runner
from kolenke.workers.tasks import TASKS

router = APIRouter(tags=["chats"])


# ---------- chats ----------
@router.get("/chats", response_model=list[ChatItem])
def list_chats(status: ChatStatus = ChatStatus.pending):
    return chats.by_status(status)


@router.get("/chats/history", response_model=list[ChatItem])
def chats_history():
    return chats.history()


@router.post("/chats/{cid}/reply", response_model=Started)
def reply_chat(cid: int, body: ChatReply):
    text = body.reply.strip()
    if not text:
        raise HTTPException(400, "Пустой ответ")
    if not chats.approve(cid, text):
        raise HTTPException(404, "Сообщение не найдено")
    task = TASKS["chat_check"]
    return Started(started=runner.start(task.title, task.run))


@router.post("/chats/{cid}/hide", response_model=Ok)
def hide_chat(cid: int):
    if not chats.set_status(cid, ChatStatus.hidden):
        raise HTTPException(404, "Сообщение не найдено")
    return Ok()


# ---------- answer base ----------
@router.get("/answers", response_model=list[Answer])
def list_answers():
    return answers.list_all()


@router.put("/answers", response_model=Ok)
def save_answers(body: AnswersSave):
    answers.save_many([a.model_dump() for a in body.items])
    return Ok()


@router.delete("/answers/{aid}", response_model=Ok)
def delete_answer(aid: int):
    answers.delete(aid)
    return Ok()


@router.get("/answers/match", response_model=AnswerMatch)
def match_answer(q: str):
    """Which answer the bot would give to this question."""
    topic, ans = answers_service.match(q)
    return AnswerMatch(topic=topic, answer=ans)


@router.get("/questions", response_model=list[Question])
def list_questions():
    return answers.questions()


@router.delete("/questions/{qid}", response_model=Ok)
def delete_question(qid: int):
    answers.delete_question(qid)
    return Ok()
