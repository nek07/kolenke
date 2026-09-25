"""hh chats: answer HR robots from the answer base, pass everything else to you with a draft reply."""
import re

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from kolenke.db.repositories import chats, settings
from kolenke.db.repositories.events import log
from kolenke.schemas.enums import ChatStatus
from kolenke.services import answers
from kolenke.services.notify import notify
from kolenke.sources.browser import wait_captcha
from kolenke.sources.hh.session import logged_in_page
from kolenke.workers.runner import runner

AUTO_NOTICES = (
    "рассмотрит ваше резюме", "рассмотрит резюме", "ответы отправлены", "к сожалению", "благодарим вас за отклик",
    "благодарим за отклик", "не прошла проверку", "была удалена", "вакансия закрыта", "перенесена в архив",
)
MSG_SEP = "\n\n———\n\n"  # between messages stored in one chat item; the page splits on it into separate bubbles

READ_CHAT_JS = """() => {
    const text = sel => { const e = document.querySelector(sel); return e ? e.innerText.trim() : ''; };
    const msgs = [...document.querySelectorAll('[data-qa^="chatik-chat-message-"]')]
        .filter(e => /^chatik-chat-message-\\d+$/.test(e.dataset.qa))
        .map(e => {
            const author = e.querySelector('[data-qa="chat-bubble-author-name"]');
            const body = e.querySelector('[data-qa="chat-bubble-text"]') || e;
            return {
                id: e.dataset.qa.replace('chatik-chat-message-', ''),
                own: e.matches('[class*="message_my"]') || !!e.querySelector('[class*="message_my"], [data-qa="chat-bubble-icon-delivered"], [data-qa="chat-bubble-icon-read"]'),
                system: !!e.querySelector('[data-qa^="participant-action-message"]'),
                author: author ? author.innerText.trim() : '',
                text: body.innerText.trim(),
            };
        });
    return {
        vacancy: text('[data-qa="chatik-header-vacancy-link-text"]'),
        company: text('[data-qa="participant-info-title"]'),
        messages: msgs,
    };
}"""


def clean_text(text: str | None) -> str:
    """hh message bodies come with nbsp/zero-width padding and runs of empty paragraphs: keep at most one blank line."""
    text = re.sub(r"[\u00a0\u200b\u2060\ufeff]", " ", text or "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def robot_active(messages: list[dict]) -> bool:
    """True while an HR robot is in the chat (it joined and has not left yet)."""
    active = False
    for m in messages:
        t = m["text"].lower()
        if m["system"] or t.startswith("пользователь "):
            if "робот" in t or "бот" in t:
                active = "присоединился" in t
        elif "робот" in m["author"].lower():
            active = True
    return active


def needs_reply(text: str | None, robot: bool) -> bool:
    """A question, or any message from a live person that isn't a stock notice («рассмотрит резюме», отказ...)."""
    low = (text or "").lower()
    return "?" in low or not (robot or any(p in low for p in AUTO_NOTICES))


def pending_incoming(messages: list[dict]) -> list[dict]:
    """Incoming (non-own, non-system) messages after our last message."""
    out = []
    for m in messages:
        if m["own"]:
            out = []
        elif not m["system"] and not m["text"].lower().startswith("пользователь "):
            out.append(m)
    return out


# ---------- browser ----------
def _unread_chats(page: Page, domain: str) -> list[dict]:
    page.goto(f"https://{domain}/chat", wait_until="domcontentloaded")
    wait_captcha(page)
    try:
        page.locator('[data-qa^="chatik-open-chat-"]').first.wait_for(timeout=15000)
    except PWTimeout:
        return []
    return page.evaluate(
        """() => [...document.querySelectorAll('[data-qa^="chatik-open-chat-"]')].map(c => ({
            id: c.dataset.qa.replace('chatik-open-chat-', ''),
            unread: !!c.querySelector('[data-qa*="unread"], [class*="unread"], [class*="counter"], [class*="badge"]'),
        })).filter(c => c.unread)"""
    )


def read_chat(page: Page) -> dict | None:
    try:
        page.locator('[data-qa^="chatik-chat-message-"]').first.wait_for(timeout=15000)
    except PWTimeout:
        return None
    page.wait_for_timeout(1000)
    return page.evaluate(READ_CHAT_JS)


def can_write(page: Page) -> bool:
    """hh removes the message box when the employer closes the chat (e.g. after a refusal)."""
    try:
        page.locator('textarea[data-qa="text-input"]').first.wait_for(state="visible", timeout=5000)
        return True
    except PWTimeout:
        return False


def send(page: Page, text: str) -> bool:
    if not can_write(page):
        return False
    before = page.locator('[class*="message_my"]').count()
    box = page.locator('textarea[data-qa="text-input"]').first
    box.fill(text)
    page.wait_for_timeout(400)
    send_btn = page.locator('[data-qa="chatik-message-input"] button[data-qa*="send"]')
    if send_btn.count() and send_btn.first.is_visible():
        send_btn.first.click()
    else:
        box.press("Enter")
    for _ in range(10):
        page.wait_for_timeout(700)
        if page.locator('[class*="message_my"]').count() > before:
            return True
    return False


def _handle_chat(page: Page, domain: str, chat_id: str, auto: bool) -> int:
    """Answers robot questions in a row while the base knows the answers; returns 1 when you need to reply."""
    page.goto(f"https://{domain}/chat/{chat_id}", wait_until="domcontentloaded")
    for _ in range(settings.get().chat_robot_steps):
        chat = read_chat(page)
        if not chat:
            return 0
        incoming = pending_incoming(chat["messages"])
        if not incoming:
            return 0
        last = incoming[-1]
        if chats.is_known(last["id"]):
            return 0  # already handled / waiting for you
        robot = robot_active(chat["messages"])
        message = MSG_SEP.join(clean_text(m["text"]) for m in incoming[-3:])
        _, answer = answers.match(last["text"])
        item = dict(chat_id=chat_id, msg_id=last["id"], company=chat["company"], vacancy=chat["vacancy"],
                    message=message, robot=robot)

        if robot and auto and answer:
            if send(page, answer):
                chats.add(**item, reply=answer, status=ChatStatus.auto_sent)
                log(f"Чат {chat['company']}: робот спросил «{last['text'][:60]}» → ответил «{answer[:40]}»")
                page.wait_for_timeout(4000)  # let the robot ask the next question
                continue
            log(f"Чат {chat['company']}: не удалось отправить ответ, передаю вам")

        # automatic notices ("компания рассмотрит резюме", "спасибо, ответы отправлены") need no reply
        is_question = needs_reply(last["text"], robot)
        if robot and is_question and not answer:
            answers.remember_unknown(last["text"], "chat")
        chats.add(**item, reply=answer, status=ChatStatus.pending if is_question else ChatStatus.info)
        if not is_question:
            return 0
        log(f"Чат {chat['company']}: новое сообщение ждёт вашего ответа")
        return 1
    return 0


def send_approved(page: Page, domain: str) -> None:
    for it in chats.approved():
        if runner.stop_requested:
            return
        try:
            page.goto(f"https://{domain}/chat/{it['chat_id']}", wait_until="domcontentloaded")
            if read_chat(page) is not None and not can_write(page):
                # closed for good: retrying would fail forever and hold up every autopilot cycle
                chats.set_status(it["id"], ChatStatus.closed)
                log(f"Чат {it['company']}: работодатель закрыл чат, ответ отправить нельзя")
                continue
            ok = read_chat(page) is not None and send(page, it["reply"])
        except Exception as e:
            ok = False
            log(f"Чат {it['company']}: ошибка {str(e)[:80]}")
        if not ok:
            log(f"Чат {it['company']}: не удалось отправить ответ, попробую в следующий раз")
            continue
        chats.set_status(it["id"], ChatStatus.sent)
        log(f"Чат {it['company']}: ваш ответ отправлен")
        page.wait_for_timeout(3000)
        _handle_chat(page, domain, it["chat_id"], settings.get().chat_auto)  # a robot may ask more


def run() -> None:
    s = settings.get()
    waiting = 0
    with logged_in_page() as session:
        if not session:
            return
        page, domain = session
        send_approved(page, domain)
        unread = _unread_chats(page, domain)
        log(f"Чаты: непрочитанных {len(unread)}")
        for c in unread[:s.chat_max]:
            if runner.stop_requested:
                break
            try:
                waiting += _handle_chat(page, domain, c["id"], s.chat_auto)
            except Exception as e:
                log(f"Чат {c['id']}: ошибка {e}")
    if waiting:
        notify(f"В чатах hh {waiting} сообщ. ждут вашего ответа")
