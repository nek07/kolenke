"""HTTP API: protection from other sites, settings, imports, statuses, pipeline, exports, jobs."""
import io
import threading
import time

import openpyxl
import pytest

import db
from conftest import add_vacancy


# ---------- protection ----------
def test_post_without_jobbot_header_is_refused(client):
    r = client.post("/api/jobs/stop", headers={"X-JobBot": ""})
    assert r.status_code == 403


def test_post_from_another_origin_is_refused(client):
    assert client.post("/api/jobs/stop", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/jobs/stop", headers={"Origin": "http://127.0.0.1:8765"}).status_code == 200


def test_foreign_host_cannot_read_data(client):
    """DNS rebinding: a page on evil.example resolving to 127.0.0.1 must not read your settings."""
    assert client.get("/api/settings", headers={"Host": "evil.example:8765"}).status_code == 403
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/settings", headers={"Host": "localhost:8765"}).status_code == 200


# ---------- settings ----------
def test_password_is_never_returned_and_empty_keeps_it(client):
    client.post("/api/settings", json={"smtp_password": "abcd efgh"})
    s = client.get("/api/settings").json()
    assert "smtp_password" not in s and s["has_password"]
    client.post("/api/settings", json={"smtp_password": "", "full_name": "Аня"})
    assert db.get_settings()["smtp_password"] == "abcd efgh"


def test_unknown_settings_keys_are_ignored(client):
    client.post("/api/settings", json={"evil_key": "1", "resume_file": "/etc/passwd"})
    s = db.get_settings()
    assert "evil_key" not in s and s["resume_file"] == ""


def test_resume_upload_type_and_path(client):
    bad = client.post("/api/resume", files={"file": ("x.exe", b"MZ")})
    assert bad.status_code == 400
    ok = client.post("/api/resume", files={"file": ("../../evil.pdf", b"%PDF")})
    assert ok.status_code == 200 and ok.json()["name"] == "evil.pdf"
    assert db.get_settings()["resume_file"].endswith("/resume/evil.pdf")


# ---------- companies import ----------
def upload(client, name, data):
    return client.post("/api/companies/import", files={"file": (name, data)}).json()


def test_import_csv_with_russian_header(client):
    csv = "Компания;Email;Должность\nHalyk Bank;HR@halyk.kz;Аналитик\nKaspi;jobs@kaspi.kz;\nБез почты;;\n".encode()
    assert upload(client, "c.csv", csv)["added"] == 2
    rows = {r["email"]: r for r in client.get("/api/companies").json()}
    assert rows["hr@halyk.kz"]["position"] == "Аналитик"  # e-mail lower-cased


def test_import_csv_without_header_and_duplicates(client):
    assert upload(client, "n.csv", "Freedom Bank, careers@ffin.kz\n".encode())["added"] == 1
    assert upload(client, "n.csv", "Freedom Bank, careers@ffin.kz\n".encode())["added"] == 0


def test_import_xlsx(client):
    wb = openpyxl.Workbook()
    wb.active.append(["Company", "E-mail"])
    wb.active.append(["Jusan", "hr@jusan.kz"])
    buf = io.BytesIO()
    wb.save(buf)
    assert upload(client, "c.xlsx", buf.getvalue())["added"] == 1


def test_add_company_rejects_bad_email(client):
    assert client.post("/api/companies/add", json={"name": "X", "email": "not-an-email"}).status_code == 400


# ---------- vacancies ----------
def test_status_change_records_event_and_applied_date(client):
    v = add_vacancy()
    client.post("/api/vacancies/status", json={"ids": [v], "status": "applied"})
    row = db.q("SELECT status, applied_at FROM vacancies WHERE id=?", (v,))[0]
    assert row["status"] == "applied" and row["applied_at"]
    assert db.q("SELECT COUNT(*) n FROM events WHERE vacancy_id=?", (v,))[0]["n"] == 1


def test_status_whitelist(client):
    v = add_vacancy()
    assert client.post("/api/vacancies/status", json={"ids": [v], "status": "hacked"}).status_code == 400


def test_queue_all_new_only_new(client):
    a, b = add_vacancy(ext_id="1"), add_vacancy(ext_id="2", status="skipped")
    assert client.post("/api/vacancies/queue_all_new", json={}).json()["count"] == 1
    assert {r["id"]: r["status"] for r in db.q("SELECT id, status FROM vacancies")} == {a: "queued", b: "skipped"}


def test_vacancy_detail_shape(client):
    v = add_vacancy(status="applied", match_info='[{"ok": true, "text": "ok"}]')
    d = client.get(f"/api/vacancies/{v}").json()
    assert d["match_info"] == [{"ok": True, "text": "ok"}] and d["events"] == [] and d["chats"] == []
    assert client.get("/api/vacancies/99999").status_code == 404


# ---------- pipeline API ----------
def test_pipeline_board_and_update(client):
    v = add_vacancy(status="applied", hh_state="просмотрен")
    add_vacancy(ext_id="2", status="new")
    board = client.get("/api/pipeline").json()
    assert [s["id"] for s in board["stages"]] == ["applied", "viewed", "invited", "interview", "offer", "declined"]
    assert [(c["id"], c["stage"]) for c in board["cards"]] == [(v, "viewed")]
    r = client.post(f"/api/vacancies/{v}/pipeline", json={"stage": "interview", "next_step": "Собеседование",
                                                          "next_at": "2030-01-01T15:00:00", "notes": "HR: Айгерим"})
    assert r.json()["stage"] == "interview" and r.json()["stage_manual"] == 1
    assert client.post(f"/api/vacancies/{v}/pipeline", json={"next_at": "garbage"}).status_code == 400
    assert client.post("/api/vacancies/99999/pipeline", json={"stage": "offer"}).status_code == 404


def test_followup_draft_and_dismiss(client):
    db.set_settings({"full_name": "Аня"})
    v = add_vacancy(status="applied", title="Data Engineer")
    assert "Data Engineer" in client.get(f"/api/vacancies/{v}/followup_draft").json()["text"]
    client.post(f"/api/vacancies/{v}/followup", json={"action": "dismissed"})
    assert db.q("SELECT followup FROM vacancies WHERE id=?", (v,))[0]["followup"] == "dismissed"
    assert client.post(f"/api/vacancies/{v}/followup", json={"action": "send", "text": "  "}).status_code == 400


# ---------- status, stats, export ----------
def test_status_endpoint(client):
    add_vacancy(status="applied", applied_at=db.now(), hh_state="приглашение", invited_at=db.now())
    s = client.get("/api/status").json()
    assert s["applied_today"] == 1 and s["week"]["invites"] == 1 and s["running"] is False
    for key in ("reminders", "chats_pending", "attention", "no_letter", "review"):
        assert key in s


def test_stats_gentle_and_export_csv(client):
    add_vacancy(status="applied", applied_at=db.now(), hh_state="отказ", title="QA; «тест»")
    assert client.get("/api/stats").status_code == 200
    r = client.get("/api/export/vacancies")
    text = r.content.decode("utf-8-sig")
    assert r.headers["content-type"].startswith("text/csv") and '"QA; «тест»"' in text  # ; inside a field is quoted
    assert client.get("/api/export/nope").status_code == 404


# ---------- answers & jobs ----------
def test_answers_crud_and_test_endpoint(client):
    items = client.get("/api/answers").json()
    items[0]["answer"] = "от 800 000 ₸"
    items.append({"id": None, "topic": "Машина", "keywords": "машин, авто", "answer": "есть"})
    client.post("/api/answers", json={"items": items})
    assert client.get("/api/answers/test", params={"q": "У вас есть машина?"}).json() == {"topic": "Машина", "answer": "есть"}


def test_unknown_job_and_busy_job(client, monkeypatch):
    import app as app_module
    assert client.post("/api/jobs/rm_rf").status_code == 404
    gate = threading.Event()
    monkeypatch.setitem(app_module.JOBS, "hh_sync", ("Тест", lambda: gate.wait(2)))
    assert client.post("/api/jobs/hh_sync").status_code == 200
    assert client.post("/api/jobs/hh_sync").status_code == 409
    gate.set()
    time.sleep(0.1)


# ---------- search ----------
def test_search_finds_company_everywhere_ignoring_case(client):
    add_vacancy(ext_id="7", title="PHP программист", company="ТОО Плаза Лубрикантс")
    add_vacancy(ext_id="8", title="Python", company="Другая")
    db.x("INSERT INTO chat_items(chat_id, msg_id, company, vacancy, message, status) VALUES "
         "('c1', 'm1', 'Плаза Лубрикантс', '', 'старое', 'info'), ('c1', 'm2', 'Плаза Лубрикантс', '', 'новое', 'pending')")
    db.x("INSERT INTO companies(name, email) VALUES ('Плаза', 'hr@plaza.kz')")
    r = client.get("/api/search", params={"q": "плаза лубр"}).json()
    assert [v["title"] for v in r["vacancies"]] == ["PHP программист"]
    assert [c["message"] for c in r["chats"]] == ["новое"]  # one row per chat, the latest
    assert r["companies"] == []  # «лубр» is not in the company's mail row
    assert client.get("/api/search", params={"q": "PLAZA.KZ"}).json()["companies"][0]["email"] == "hr@plaza.kz"
    assert client.get("/api/search", params={"q": "  "}).json() == {"vacancies": [], "chats": [], "companies": []}
