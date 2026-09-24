"""hh chats: answer HR robots from the answer base, pass everything else to the user with a draft reply."""
import subprocess

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import answers
import db
from hh_bot import _open, _wait_captcha, is_logged_in
from jobs import job

MAX_CHATS = 20
MAX_ROBOT_STEPS = 10  # questions in a row answered in one chat
AUTO_NOTICES = (
    "рассмотрит ваше резюме", "рассмотрит резюме", "ответы отправлены", "к сожалению", "благодарим вас за отклик",
    "благодарим за отклик", "не прошла проверку", "была удалена", "вакансия закрыта", "перенесена в архив",
)


def notify(text):
    """macOS notification, so the user knows something needs their answer."""
    try:
        # the text comes from employers (company names, messages): pass it as data, never as AppleScript source
        subprocess.run(["osascript", "-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "kolenke"',
                        "-e", "end run", str(text)[:250]], timeout=5)
    except Exception:
        pass


def _unread_chats(page, domain):
    page.goto(f"https://{domain}/chat", wait_until="domcontentloaded")
    _wait_captcha(page)
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


def _read_chat(page):
    try:
        page.locator('[data-qa^="chatik-chat-message-"]').first.wait_for(timeout=15000)
    except PWTimeout:
        return None
    page.wait_for_timeout(1000)
    return page.evaluate(
        """() => {
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
    )


def _robot_active(messages):
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


def needs_reply(text, robot) -> bool:
    """A question, or any message from a live person that isn't a stock notice («рассмотрит резюме», отказ...)."""
    low = (text or "").lower()
    return "?" in low or not (robot or any(p in low for p in AUTO_NOTICES))


def _pending_incoming(messages):
    """Incoming (non-own, non-system) messages after our last message."""
    out = []
    for m in messages:
        if m["own"]:
            out = []
        elif not m["system"] and not m["text"].lower().startswith("пользователь "):
            out.append(m)
    return out


def can_write(page) -> bool:
    """hh removes the message box when the employer closes the chat (e.g. after a refusal)."""
    try:
        page.locator('textarea[data-qa="text-input"]').first.wait_for(state="visible", timeout=5000)
        return True
    except PWTimeout:
        return False


def _send(page, text) -> bool:
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


def _handle_chat(page, domain, chat_id, auto):
    page.goto(f"https://{domain}/chat/{chat_id}", wait_until="domcontentloaded")
    new_items = 0
    for _ in range(MAX_ROBOT_STEPS):
        chat = _read_chat(page)
        if not chat:
            return new_items
        incoming = _pending_incoming(chat["messages"])
        if not incoming:
            return new_items
        last = incoming[-1]
        if db.q("SELECT 1 FROM chat_items WHERE msg_id=?", (last["id"],)):
            return new_items  # already handled / waiting for the user
        robot = _robot_active(chat["messages"])
        message = "\n\n".join(m["text"] for m in incoming[-3:])
        topic, answer = answers.match(last["text"])
        base = (chat_id, last["id"], chat["company"], chat["vacancy"], message, int(robot))

        if robot and auto and answer:
            if _send(page, answer):
                db.x(
                    "INSERT OR IGNORE INTO chat_items(chat_id, msg_id, company, vacancy, message, robot, reply, status, "
                    "created_at, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'auto_sent', ?, ?)",
                    base + (answer, db.now(), db.now()),
                )
                db.log(f"Чат {chat['company']}: робот спросил «{last['text'][:60]}» → ответил «{answer[:40]}»")
                page.wait_for_timeout(4000)  # let the robot ask the next question
                continue
            db.log(f"Чат {chat['company']}: не удалось отправить ответ, передаю вам")

        # automatic notices ("компания рассмотрит резюме", "спасибо, ответы отправлены") need no reply
        is_question = needs_reply(last["text"], robot)
        if robot and is_question and not answer:
            answers.remember_unknown(last["text"], "chat")
        db.x(
            "INSERT OR IGNORE INTO chat_items(chat_id, msg_id, company, vacancy, message, robot, reply, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            base + (answer, "pending" if is_question else "info", db.now()),
        )
        if not is_question:
            return new_items
        db.log(f"Чат {chat['company']}: новое сообщение ждёт вашего ответа")
        return new_items + 1
    return new_items


def _send_approved(page, domain):
    for it in db.q("SELECT * FROM chat_items WHERE status='approved' ORDER BY id"):
        if job.stop_requested:
            return
        try:
            page.goto(f"https://{domain}/chat/{it['chat_id']}", wait_until="domcontentloaded")
            if _read_chat(page) is not None and not can_write(page):
                # closed for good: retrying would fail forever and hold up every autopilot cycle
                db.x("UPDATE chat_items SET status='closed' WHERE id=?", (it["id"],))
                db.log(f"Чат {it['company']}: работодатель закрыл чат, ответ отправить нельзя")
                continue
            ok = _read_chat(page) is not None and _send(page, it["reply"])
        except Exception as e:
            ok = False
            db.log(f"Чат {it['company']}: ошибка {str(e)[:80]}")
        if not ok:
            db.log(f"Чат {it['company']}: не удалось отправить ответ, попробую в следующий раз")
            continue
        db.x("UPDATE chat_items SET status='sent', sent_at=? WHERE id=?", (db.now(), it["id"]))
        db.log(f"Чат {it['company']}: ваш ответ отправлен")
        page.wait_for_timeout(3000)
        _handle_chat(page, domain, it["chat_id"], db.get_settings()["chat_auto"] == "1")  # a robot may ask more


def run():
    s = db.get_settings()
    domain = s["hh_domain"]
    with sync_playwright() as p:
        ctx, page = _open(p)
        if not is_logged_in(page, domain):
            db.log("hh: вы не вошли в аккаунт — нажмите «Войти в hh»")
            ctx.close()
            return
        _send_approved(page, domain)
        chats = _unread_chats(page, domain)
        db.log(f"Чаты: непрочитанных {len(chats)}")
        waiting = 0
        for c in chats[:MAX_CHATS]:
            if job.stop_requested:
                break
            try:
                waiting += _handle_chat(page, domain, c["id"], s["chat_auto"] == "1")
            except Exception as e:
                db.log(f"Чат {c['id']}: ошибка {e}")
        ctx.close()
    if waiting:
        notify(f"В чатах hh {waiting} сообщ. ждут вашего ответа")
