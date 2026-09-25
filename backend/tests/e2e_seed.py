"""Fills an empty data folder with a small, realistic set of records for the frontend's end-to-end tests.
Run with KOLENKE_DATA_DIR pointing to a throwaway folder: python tests/e2e_seed.py"""
import json
import os
import sys
from datetime import datetime, timedelta

if not os.environ.get("KOLENKE_DATA_DIR"):
    sys.exit("KOLENKE_DATA_DIR must point to a throwaway folder: this script writes test records")

from kolenke import db  # noqa: E402
from kolenke.config import ensure_dirs, get_config  # noqa: E402
from kolenke.db.connection import execute, insert  # noqa: E402
from kolenke.db.repositories import events, settings  # noqa: E402

ensure_dirs(get_config())
db.init()
for table in ("vacancies", "companies", "chat_items", "events", "log", "questions"):
    execute(f"DELETE FROM {table}")

now = datetime.now()
iso = lambda d: d.isoformat(timespec="seconds")  # noqa: E731

settings.save({
    "full_name": "Аня Тестова", "phone": "+7 700 000 00 00", "desired_position": "Аналитик",
    "hh_resumes": [{"hash": "r1", "title": "Аналитик данных"}], "hh_resume_hash": "r1",
})


def vacancy(ext, title, company, status, **kw):
    row = {"source": "hh", "ext_id": ext, "url": f"https://hh.kz/vacancy/{ext}", "title": title, "company": company,
           "status": status, "created_at": iso(now - timedelta(hours=2)), **kw}
    vid = insert(f"INSERT INTO vacancies({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
    events.add(vid, "found", "Найдена среди подходящих к резюме «Аналитик данных»")
    return vid


reasons = json.dumps([{"ok": True, "text": "зарплата от 500 000 ₸"}, {"ok": True, "text": "совпадение навыков 82%"}], ensure_ascii=False)
vacancy("101", "Data Analyst", "Kaspi Bank", "new", skill_match=82, salary_text="от 500 000 ₸", match_info=reasons)
vacancy("102", "BI-аналитик", "Halyk Bank", "new", skill_match=45, match_info=reasons)
vacancy("103", "Аналитик SQL", "ТОО Плаза", "new")
applied = vacancy("104", "Product Analyst", "Freedom Finance", "applied", applied_at=iso(now - timedelta(days=1)),
                  hh_state="приглашение", invited_at=iso(now), stage="invited", resume="Аналитик данных", letter_sent=1)
vacancy("105", "Junior Analyst", "Jusan", "applied", applied_at=iso(now - timedelta(days=7)), stage="applied", letter_sent=0)
vacancy("106", "Senior Data Scientist", "Air Astana", "skipped", note="в названии есть «senior»")
insert("INSERT INTO vacancies(source, ext_id, url, title, company, status, created_at, contacts, location, country) "
       "VALUES ('enbek', '9', 'https://www.enbek.kz/ru/vacancy/x~9', 'Экономист', 'KMF', 'new', ?, ?, 'г. Алматы', 'Казахстан')",
       (iso(now), json.dumps({"emails": ["hr@kmf.kz"], "phones": [], "telegram": [], "person": "Лаура"}, ensure_ascii=False)))

insert("INSERT INTO companies(name, email, position, status, created_at) VALUES ('Halyk Bank', 'hr@halyk.kz', 'Аналитик', 'new', ?)", (iso(now),))
insert("INSERT INTO chat_items(chat_id, msg_id, company, vacancy, message, robot, status, created_at) "
       "VALUES ('c1', 'm1', 'Freedom Finance', 'Product Analyst', 'Когда вам удобно созвониться?', 0, 'pending', ?)", (iso(now),))
insert("INSERT INTO questions(text, source, seen, created_at) VALUES ('Есть ли у вас водительские права?', 'form', 2, ?)", (iso(now),))
events.log("hh: поиск завершён, новых вакансий: 3, прошли фильтры: 3")
print(f"seeded {get_config().db_path} (invited vacancy id {applied})")
