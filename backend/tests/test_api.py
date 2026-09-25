"""HTTP API: protection from other sites, settings, imports, statuses, pipeline, exports, tasks."""
import io
import threading
import time

import openpyxl
from conftest import add_vacancy

from kolenke.db.connection import execute, now, query, scalar
from kolenke.db.repositories import settings


# ---------- protection ----------
def test_post_without_jobbot_header_is_refused(client):
    assert client.post("/api/jobs/stop", headers={"X-JobBot": ""}).status_code == 403


def test_post_from_another_origin_is_refused(client):
    assert client.post("/api/jobs/stop", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/jobs/stop", headers={"Origin": "http://localhost:3000"}).status_code == 200  # the Next.js page


def test_foreign_host_cannot_read_data(client):
    """DNS rebinding: a page on evil.example resolving to 127.0.0.1 must not read your settings."""
    assert client.get("/api/settings", headers={"Host": "evil.example:8765"}).status_code == 403
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/settings", headers={"Host": "localhost:8765"}).status_code == 200


def test_openapi_is_available_for_the_frontend_client(client):
    assert "/api/vacancies" in client.get("/openapi.json").json()["paths"]


# ---------- settings ----------
def test_password_is_never_returned_and_empty_keeps_it(client):
    client.patch("/api/settings", json={"smtp_password": "abcd efgh"})
    s = client.get("/api/settings").json()
    assert "smtp_password" not in s and s["has_password"]
    client.patch("/api/settings", json={"smtp_password": "", "full_name": "Аня"})
    assert settings.get().smtp_password == "abcd efgh" and settings.get().full_name == "Аня"


def test_settings_are_typed_and_validated(client):
    r = client.patch("/api/settings", json={"hh_daily_limit": 30, "f_skip_no_salary": True, "f_experience": ["noExperience"]})
    assert r.status_code == 200
    body = r.json()
    assert body["hh_daily_limit"] == 30 and body["f_skip_no_salary"] is True and body["f_experience"] == ["noExperience"]
    assert client.patch("/api/settings", json={"hh_daily_limit": 0}).status_code == 422
    assert client.patch("/api/settings", json={"hh_domain": "evil.com"}).status_code == 422
    assert client.patch("/api/settings", json={"autopilot_mode": "yolo"}).status_code == 422


def test_unknown_and_bot_owned_settings_are_ignored(client):
    client.patch("/api/settings", json={"evil_key": "1", "resume_file": "/etc/passwd"})
    assert settings.get().resume_file == ""
    assert not scalar("SELECT COUNT(*) FROM settings WHERE key='evil_key'")


def test_resume_upload_type_and_path(client):
    assert client.post("/api/settings/resume", files={"file": ("x.exe", b"MZ")}).status_code == 400
    ok = client.post("/api/settings/resume", files={"file": ("../../evil.pdf", b"%PDF")})
    assert ok.status_code == 200 and ok.json()["name"] == "evil.pdf"
    assert settings.get().resume_file.endswith("/resume/evil.pdf")
    assert client.get("/api/settings").json()["resume_name"] == "evil.pdf"


# ---------- companies import ----------
def upload(client, name, data):
    return client.post("/api/companies/import", files={"file": (name, data)}).json()


def test_import_csv_with_russian_header(client):
    csv = "Компания;Email;Должность\nHalyk Bank;HR@halyk.kz;Аналитик\nKaspi;jobs@kaspi.kz;\nБез почты;;\n".encode()
    assert upload(client, "c.csv", csv)["added"] == 2
    rows = {r["email"]: r for r in client.get("/api/companies").json()}
    assert rows["hr@halyk.kz"]["position"] == "Аналитик"  # e-mail lower-cased


def test_import_csv_without_header_and_duplicates(client):
    assert upload(client, "n.csv", b"Freedom Bank, careers@ffin.kz\n")["added"] == 1
    assert upload(client, "n.csv", b"Freedom Bank, careers@ffin.kz\n")["added"] == 0


def test_import_xlsx(client):
    wb = openpyxl.Workbook()
    wb.active.append(["Company", "E-mail"])
    wb.active.append(["Jusan", "hr@jusan.kz"])
    buf = io.BytesIO()
    wb.save(buf)
    assert upload(client, "c.xlsx", buf.getvalue())["added"] == 1


def test_import_empty_file(client):
    assert client.post("/api/companies/import", files={"file": ("e.csv", b"\n\n")}).status_code == 400


def test_add_edit_and_status_of_company(client):
    assert client.post("/api/companies", json={"name": "X", "email": "not-an-email"}).status_code == 400
    assert client.post("/api/companies", json={"name": "Kaspi", "email": "HR@kaspi.kz"}).status_code == 200
    cid = client.get("/api/companies").json()[0]["id"]
    assert client.patch(f"/api/companies/{cid}", json={"name": "Kaspi Bank", "position": "QA"}).status_code == 200
    assert client.patch("/api/companies/99999", json={"name": "X"}).status_code == 404
    client.patch("/api/companies/status", json={"ids": [cid], "status": "queued"})
    assert client.get("/api/companies", params={"status": "queued"}).json()[0]["name"] == "Kaspi Bank"
    assert client.patch("/api/companies/status", json={"ids": [cid], "status": "hacked"}).status_code == 422


def test_mail_preview(client):
    client.patch("/api/settings", json={"full_name": "Аня", "smtp_user": "anya@gmail.com", "desired_position": "Аналитик"})
    client.post("/api/companies", json={"name": "Halyk", "email": "hr@halyk.kz"})
    cid = client.get("/api/companies").json()[0]["id"]
    p = client.get(f"/api/companies/{cid}/preview").json()
    assert p["to"] == "hr@halyk.kz" and "Аналитик" in p["subject"] and "Halyk" in p["body"] and p["attachments"] == []


# ---------- vacancies ----------
def test_status_change_records_event_and_applied_date(client):
    v = add_vacancy()
    client.patch("/api/vacancies/status", json={"ids": [v], "status": "applied"})
    row = query("SELECT status, applied_at FROM vacancies WHERE id=?", (v,))[0]
    assert row["status"] == "applied" and row["applied_at"]
    assert scalar("SELECT COUNT(*) FROM events WHERE vacancy_id=?", (v,)) == 1


def test_review_swipe_is_recorded(client):
    v = add_vacancy()
    client.patch("/api/vacancies/status", json={"ids": [v], "status": "queued", "review": True})
    assert query("SELECT text FROM events WHERE vacancy_id=?", (v,))[0]["text"].startswith("Вы одобрили при проверке")
    assert query("SELECT reviewed_at FROM vacancies WHERE id=?", (v,))[0]["reviewed_at"]


def test_status_whitelist(client):
    v = add_vacancy()
    assert client.patch("/api/vacancies/status", json={"ids": [v], "status": "hacked"}).status_code == 422
    assert client.patch("/api/vacancies/status", json={"ids": [], "status": "new"}).status_code == 422


def test_queue_all_new_only_new(client):
    a, b = add_vacancy(ext_id="1"), add_vacancy(ext_id="2", status="skipped")
    assert client.post("/api/vacancies/queue-new", json={}).json()["count"] == 1
    assert {r["id"]: r["status"] for r in query("SELECT id, status FROM vacancies")} == {a: "queued", b: "skipped"}


def test_review_queue_best_match_first(client):
    low, high, unknown = add_vacancy(ext_id="1", skill_match=40), add_vacancy(ext_id="2", skill_match=90), add_vacancy(ext_id="3")
    assert [v["id"] for v in client.get("/api/vacancies/review").json()] == [high, low, unknown]


def test_add_and_delete_vacancy(client):
    assert client.post("/api/vacancies", json={"url": "javascript:alert(1)"}).status_code == 422
    client.post("/api/vacancies", json={"url": "https://bank.kz/job/1", "title": "Аналитик"})
    v = client.get("/api/vacancies", params={"source": "other"}).json()
    assert [x["title"] for x in v] == ["Аналитик"]
    client.post("/api/vacancies/delete", json={"ids": [v[0]["id"]]})
    assert client.get("/api/vacancies").json() == []


def test_vacancy_detail_shape(client):
    v = add_vacancy(status="applied", match_info='[{"ok": true, "text": "ok"}]')
    d = client.get(f"/api/vacancies/{v}").json()
    assert d["match_info"] == [{"ok": True, "text": "ok"}] and d["events"] == [] and d["chats"] == []
    assert client.get("/api/vacancies/99999").status_code == 404


def test_vacancy_detail_finds_its_chats(client):
    v = add_vacancy(title="Backend", company="ТОО Плаза")
    add_vacancy(ext_id="2", title="Frontend", company="ТОО Плаза")
    execute("INSERT INTO chat_items(chat_id, msg_id, company, vacancy, message, status) VALUES "
            "('c1', 'm1', 'Плаза', 'Backend', 'Приглашаем', 'pending'), ('c2', 'm2', 'Плаза', 'Frontend', 'Отказ', 'info')")
    assert [c["message"] for c in client.get(f"/api/vacancies/{v}").json()["chats"]] == ["Приглашаем"]


# ---------- pipeline API ----------
def test_pipeline_board_and_update(client):
    v = add_vacancy(status="applied", hh_state="просмотрен")
    add_vacancy(ext_id="2", status="new")
    board = client.get("/api/pipeline").json()
    assert [s["id"] for s in board["stages"]] == ["applied", "viewed", "invited", "interview", "offer", "declined"]
    assert [(c["id"], c["stage"]) for c in board["cards"]] == [(v, "viewed")]
    r = client.patch(f"/api/vacancies/{v}/pipeline", json={"stage": "interview", "next_step": "Собеседование",
                                                           "next_at": "2030-01-01T15:00:00", "notes": "HR: Айгерим"})
    assert r.json()["stage"] == "interview" and r.json()["stage_manual"] == 1 and r.json()["notes"] == "HR: Айгерим"
    assert client.patch(f"/api/vacancies/{v}/pipeline", json={"next_at": "garbage"}).status_code == 400
    assert client.patch(f"/api/vacancies/{v}/pipeline", json={"stage": "hired"}).status_code == 422
    assert client.patch("/api/vacancies/99999/pipeline", json={"stage": "offer"}).status_code == 404


def test_reminders_endpoint(client):
    add_vacancy(status="applied", next_step="Звонок", next_at="2000-01-01T10:00:00")
    r = client.get("/api/reminders").json()
    assert [p["next_step"] for p in r["past"]] == ["Звонок"] and r["upcoming"] == []


def test_followup_draft_send_and_dismiss(client, monkeypatch):
    from kolenke.workers import tasks
    monkeypatch.setitem(tasks.TASKS, "hh_followups", tasks.Task("hh_followups", "Тест", lambda: None))
    settings.save({"full_name": "Аня"})
    v = add_vacancy(status="applied", title="Data Engineer")
    assert "Data Engineer" in client.get(f"/api/vacancies/{v}/followup-draft").json()["text"]
    assert client.post(f"/api/vacancies/{v}/followup", json={"text": "  "}).status_code == 400
    assert client.post(f"/api/vacancies/{v}/followup", json={"text": "Добрый день!"}).json()["ok"]
    assert query("SELECT followup, followup_text FROM vacancies WHERE id=?", (v,))[0] == {"followup": "approved", "followup_text": "Добрый день!"}
    client.post(f"/api/vacancies/{v}/followup/close", json={"action": "dismissed"})
    assert query("SELECT followup FROM vacancies WHERE id=?", (v,))[0]["followup"] == "dismissed"
    assert client.post(f"/api/vacancies/{v}/followup/close", json={"action": "rm"}).status_code == 422


# ---------- chats ----------
def test_chat_reply_and_hide(client, monkeypatch):
    from kolenke.workers import tasks
    monkeypatch.setitem(tasks.TASKS, "chat_check", tasks.Task("chat_check", "Тест", lambda: None))
    execute("INSERT INTO chat_items(chat_id, msg_id, company, message, status) VALUES ('c1', 'm1', 'Kaspi', 'Когда удобно?', 'pending')")
    cid = client.get("/api/chats").json()[0]["id"]
    assert client.post(f"/api/chats/{cid}/reply", json={"reply": " "}).status_code == 400
    assert client.post(f"/api/chats/{cid}/reply", json={"reply": "Завтра в 10"}).status_code == 200
    assert client.get("/api/chats", params={"status": "approved"}).json()[0]["reply"] == "Завтра в 10"
    assert [c["id"] for c in client.get("/api/chats/history").json()] == [cid]
    client.post(f"/api/chats/{cid}/hide")
    assert client.get("/api/chats/history").json() == []
    assert client.post("/api/chats/99999/hide").status_code == 404


# ---------- status, stats, export ----------
def test_status_endpoint(client):
    add_vacancy(status="applied", applied_at="2099-01-01T10:00:00", hh_state="приглашение", invited_at="2099-01-01T10:00:00")
    add_vacancy(ext_id="2", status="applied", applied_at=now())
    s = client.get("/api/status").json()
    assert s["applied_today"] == 1 and s["week"]["invites"] == 1 and s["running"] is False
    assert s["week"]["rate"] == 50.0


def test_stats_and_export_csv(client):
    add_vacancy(status="applied", applied_at="2026-01-05T10:00:00", hh_state="отказ", title="QA; «тест»")
    st = client.get("/api/stats").json()
    assert st["by_day"] == [{"day": "2026-01-05", "hh": 1, "mail": 0}] and st["hh_states"] == [{"state": "отказ", "n": 1}]
    r = client.get("/api/export/vacancies")
    text = r.content.decode("utf-8-sig")
    assert r.headers["content-type"].startswith("text/csv") and '"QA; «тест»"' in text  # ; inside a field is quoted
    assert client.get("/api/export/nope").status_code == 404


# ---------- answers & tasks ----------
def test_answers_crud_and_match(client):
    items = client.get("/api/answers").json()
    items[0]["answer"] = "от 800 000 ₸"
    items.append({"id": None, "topic": "Машина", "keywords": "машин, авто", "answer": "есть"})
    client.put("/api/answers", json={"items": items})
    assert client.get("/api/answers/match", params={"q": "У вас есть машина?"}).json() == {"topic": "Машина", "answer": "есть"}
    aid = client.get("/api/answers").json()[-1]["id"]
    client.delete(f"/api/answers/{aid}")
    assert client.get("/api/answers/match", params={"q": "У вас есть машина?"}).json()["topic"] is None


def test_questions_list_and_delete(client):
    execute("INSERT INTO questions(text, source, seen) VALUES ('Есть ли машина?', 'form', 3)")
    q = client.get("/api/questions").json()
    assert [(x["text"], x["seen"]) for x in q] == [("Есть ли машина?", 3)]
    client.delete(f"/api/questions/{q[0]['id']}")
    assert client.get("/api/questions").json() == []


def test_unknown_task_and_busy_task(client, monkeypatch):
    from kolenke.workers import tasks
    assert client.post("/api/jobs/rm_rf").status_code == 404
    assert {t["key"] for t in client.get("/api/jobs").json()} == set(tasks.TASKS)
    gate = threading.Event()
    monkeypatch.setitem(tasks.TASKS, "hh_sync", tasks.Task("hh_sync", "Тест", lambda: gate.wait(2)))
    assert client.post("/api/jobs/hh_sync").status_code == 200
    assert client.post("/api/jobs/hh_sync").status_code == 409
    gate.set()
    time.sleep(0.1)


# ---------- search ----------
def test_search_finds_company_everywhere_ignoring_case(client):
    add_vacancy(ext_id="7", title="PHP программист", company="ТОО Плаза Лубрикантс")
    add_vacancy(ext_id="8", title="Python", company="Другая")
    execute("INSERT INTO chat_items(chat_id, msg_id, company, vacancy, message, status) VALUES "
            "('c1', 'm1', 'Плаза Лубрикантс', '', 'старое', 'info'), ('c1', 'm2', 'Плаза Лубрикантс', '', 'новое', 'pending')")
    execute("INSERT INTO companies(name, email) VALUES ('Плаза', 'hr@plaza.kz')")
    r = client.get("/api/search", params={"q": "плаза лубр"}).json()
    assert [v["title"] for v in r["vacancies"]] == ["PHP программист"]
    assert [c["message"] for c in r["chats"]] == ["новое"]  # one row per chat, the latest
    assert r["companies"] == []  # «лубр» is not in the company's mail row
    assert client.get("/api/search", params={"q": "PLAZA.KZ"}).json()["companies"][0]["email"] == "hr@plaza.kz"
    assert client.get("/api/search", params={"q": "  "}).json() == {"vacancies": [], "chats": [], "companies": []}
