"""After the response: stages, manual priority, reminders, follow-ups, e-mail building."""
from datetime import datetime, timedelta

import pytest

import db
import mailer
import pipeline
from conftest import add_vacancy


def stage(vid):
    return db.q("SELECT stage FROM vacancies WHERE id=?", (vid,))[0]["stage"]


def test_ensure_stages_from_hh_states():
    ids = {s: add_vacancy(ext_id=str(i), status="applied", hh_state=s)
           for i, s in enumerate(["не просмотрен", "просмотрен", "приглашение", "собеседование", "отказ", None])}
    new = add_vacancy(ext_id="99", status="new")
    pipeline.ensure_stages()
    assert [stage(ids[s]) for s in ids] == ["applied", "viewed", "invited", "interview", "declined", "applied"]
    assert stage(new) is None  # only sent responses are on the board


def test_hh_moves_forward_but_never_back():
    v = add_vacancy(status="applied", hh_state="просмотрен")
    pipeline.ensure_stages()
    pipeline.advance_from_hh(v, "не просмотрен")
    assert stage(v) == "viewed"
    pipeline.advance_from_hh(v, "приглашение")
    assert stage(v) == "invited"


def test_manual_stage_survives_hh_but_hh_can_push_forward():
    v = add_vacancy(status="applied")
    pipeline.ensure_stages()
    pipeline.update(v, {"stage": "interview"})
    pipeline.advance_from_hh(v, "просмотрен")
    pipeline.advance_from_hh(v, "отказ")
    assert stage(v) == "interview"
    pipeline.advance_from_hh(v, "выход на работу")
    assert stage(v) == "offer"


def test_auto_decline_then_invitation_brings_card_back():
    v = add_vacancy(status="applied")
    pipeline.ensure_stages()
    pipeline.advance_from_hh(v, "отказ")
    assert stage(v) == "declined"
    pipeline.advance_from_hh(v, "приглашение")
    assert stage(v) == "invited"


def test_stage_events_are_recorded():
    v = add_vacancy(status="applied")
    pipeline.ensure_stages()
    pipeline.update(v, {"stage": "invited"})
    assert db.q("SELECT kind, text FROM events WHERE vacancy_id=?", (v,)) == [{"kind": "stage", "text": "Этап: Приглашение"}]


def test_invalid_next_date_is_rejected():
    v = add_vacancy(status="applied")
    with pytest.raises(ValueError):
        pipeline.update(v, {"next_step": "Собеседование", "next_at": "<img src=x>"})


def test_reminders_upcoming_past_and_one_notification_each():
    v = add_vacancy(status="applied")
    pipeline.ensure_stages()
    at = (datetime.now() + timedelta(hours=20)).replace(microsecond=0)
    pipeline.update(v, {"next_step": "Собеседование", "next_at": at.isoformat()})
    r = pipeline.reminders()
    assert [u["id"] for u in r["upcoming"]] == [v] and not r["past"]

    sent = []
    pipeline.notify_due(sent.append)
    pipeline.notify_due(sent.append)
    assert len(sent) == 1 and "Собеседование: ТОО Тест" in sent[0]

    pipeline.update(v, {"next_at": (datetime.now() + timedelta(minutes=30)).isoformat()})  # new date → new reminders
    pipeline.notify_due(sent.append)
    assert len(sent) == 2 and sent[1].startswith("Через")

    pipeline.update(v, {"next_at": (datetime.now() - timedelta(hours=2)).isoformat()})
    assert [p["id"] for p in pipeline.reminders()["past"]] == [v]


def test_declined_cards_do_not_remind():
    v = add_vacancy(status="applied")
    pipeline.ensure_stages()
    pipeline.update(v, {"stage": "declined", "next_step": "Звонок", "next_at": (datetime.now() + timedelta(hours=3)).isoformat()})
    sent = []
    pipeline.notify_due(sent.append)
    assert not sent and not pipeline.reminders()["upcoming"]


def test_followup_after_n_days_without_reaction():
    old = (datetime.now() - timedelta(days=6)).isoformat(timespec="seconds")
    quiet = add_vacancy(ext_id="1", status="applied", applied_at=old)
    fresh = add_vacancy(ext_id="2", status="applied", applied_at=db.now())
    invited = add_vacancy(ext_id="3", status="applied", applied_at=old, hh_state="приглашение")
    done = add_vacancy(ext_id="4", status="applied", applied_at=old, followup="sent")
    pipeline.ensure_stages()
    assert [f["id"] for f in pipeline.followup_candidates()] == [quiet]
    assert fresh and invited and done


def test_email_build_with_attachment(tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 test")
    db.set_settings({"full_name": "Аня", "smtp_user": "anya@gmail.com", "resume_file": str(cv), "desired_position": "Аналитик"})
    msg = mailer.build(db.get_settings(), {"name": "Halyk Bank", "email": "hr@halyk.kz", "position": ""})
    assert msg["To"] == "hr@halyk.kz" and "Аналитик" in msg["Subject"]
    assert [a.get_filename() for a in msg.iter_attachments()] == ["cv.pdf"]
    assert "Halyk Bank" in msg.get_body(("plain",)).get_content()
