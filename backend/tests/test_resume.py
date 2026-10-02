"""Resume review: reading files, skills, role and grade checks, the market sample, the AI part and the API."""
import io
import zipfile

import pytest
from conftest import FIXTURES, add_vacancy

from kolenke.db.connection import scalar
from kolenke.db.repositories import reviews, settings
from kolenke.schemas.enums import CheckStatus, Grade
from kolenke.services.resume import ai, analyze, market, review, skills
from kolenke.services.resume.extract import ExtractError, extract_text
from kolenke.services.resume.profiles import match_role

RESUMES = FIXTURES / "resumes"
WEAK = (RESUMES / "weak_junior.txt").read_text()
STRONG = (RESUMES / "strong_middle.txt").read_text()


def checks_of(text, role="Backend-разработчик Python", grade=Grade.middle, sample=None):
    p = analyze.parse(text)
    return p, {c.id: c for c in analyze.run_checks(p, analyze.build_context(role, grade, sample))}


# ---------- files ----------
def _docx(paragraphs):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {ns}><w:body>{body}</w:body></w:document>")
    return buf.getvalue()


def test_docx_and_txt_are_read():
    text = extract_text("cv.docx", _docx(["Алия Садыкова", "Backend-разработчик", "Опыт работы " * 10]))
    assert text.startswith("Алия Садыкова\nBackend-разработчик")
    assert "Kaspi.kz" in extract_text("cv.txt", STRONG.encode("utf-8"))


def test_unreadable_files_explain_why():
    with pytest.raises(ExtractError, match="doc"):
        extract_text("cv.doc", b"x" * 500)
    with pytest.raises(ExtractError, match="мало|почти нет"):
        extract_text("cv.txt", "Иван".encode())
    with pytest.raises(ExtractError, match="PDF, DOCX"):
        extract_text("cv.png", b"x")


@pytest.mark.parametrize("error", [KeyError("/Root"), ValueError("bad xref"), TypeError("None")])
def test_broken_pdf_is_a_message_not_a_crash(monkeypatch, error):
    import pypdf

    def broken(*a, **k):
        raise error
    monkeypatch.setattr(pypdf, "PdfReader", broken)
    with pytest.raises(ExtractError, match="Не удалось прочитать PDF"):
        extract_text("cv.pdf", b"%PDF-1.4 broken")


# ---------- skills and roles ----------
def test_skill_spellings_meet_in_one_name():
    assert skills.canonical("PostgreSQL 15") == "PostgreSQL"
    assert skills.canonical("k8s") == "Kubernetes"
    assert skills.canonical("Английский — B1 — Средний") == "Английский"
    assert skills.find_in("Писал на golang и C++, деплой в k8s через GitLab CI") == ["Go", "C++", "Kubernetes", "GitLab CI", "Git"]


def test_skill_search_has_no_everyday_false_positives():
    assert not skills.mentions("I go home and express myself", "Go")
    assert not skills.mentions("Требования к кандидату", "Сбор требований")
    assert not skills.mentions("ivan.petrov@mail.ru", "Rust")
    assert skills.covers("Работал с PostgreSQL", "SQL")  # the specific skill answers the general requirement


@pytest.mark.parametrize("role,key", [
    ("Backend-разработчик Python", "backend"), ("QA Automation Python", "qa"), ("Fullstack Python", "fullstack"),
    ("Python developer", "backend"), ("React разработчик", "frontend"), ("Системный аналитик", "analyst"),
    ("Аналитик данных", "data_analyst"), ("ML-инженер", "ml"), ("Продакт-менеджер", "manager"), ("Бухгалтер", None),
])
def test_role_title_selects_the_profile(role, key):
    profile = match_role(role)
    assert (profile.key if profile else None) == key


# ---------- experience ----------
def test_experience_from_hh_export_total():
    assert analyze.experience_months("Опыт работы — 3 года 5 месяцев\nKaspi") == 41


def test_experience_from_date_ranges_merges_overlaps_and_ignores_education():
    text = ("Опыт работы\nКомпания А\nянварь 2020 — декабрь 2021\nКомпания Б (совмещение)\nиюнь 2021 — июнь 2022\n"
            "Образование\nКБТУ, 2015 — 2019")
    p = analyze.parse(text)
    assert p.months == (2022 * 12 + 6) - (2020 * 12 + 1)  # 2020-01 … 2022-06 counted once, the university not at all


# ---------- checks ----------
def test_weak_resume_fails_the_important_checks():
    _, c = checks_of(WEAK, "Python-разработчик", Grade.junior)
    assert c["numbers"].status == CheckStatus.fail
    assert c["verbs"].status == CheckStatus.fail
    assert c["cliches"].status == CheckStatus.fail and "стрессоустойчив" in c["cliches"].detail
    assert c["portfolio"].status == CheckStatus.fail  # for a junior the code link matters most
    assert c["personal"].status == CheckStatus.warn and "женат" in c["personal"].detail
    assert c["role"].status == CheckStatus.fail and "Docker" in c["role"].detail
    assert all(x.fix for x in c.values() if x.status != CheckStatus.passed)


def test_strong_resume_passes_and_scores_high():
    p, c = checks_of(STRONG)
    assert p.months == (2026 * 12 + 9) - (2020 * 12 + 6) or p.months > 60
    for key in ("contacts", "numbers", "verbs", "cliches", "portfolio", "personal", "english", "experience", "signals", "role"):
        assert c[key].status == CheckStatus.passed, (key, c[key].detail)
    assert analyze.score(list(c.values())) >= 85


def test_grade_is_checked_against_experience():
    _, c = checks_of(WEAK, "Python-разработчик", Grade.lead)  # ~3 years against the 6+ expected
    assert c["experience"].status == CheckStatus.fail
    assert c["signals"].status == CheckStatus.fail


def test_templates_for_weak_lines_keep_placeholders_instead_of_inventing_facts():
    rewrites = analyze.rewrite_templates(analyze.parse(WEAK))
    assert rewrites and all("[" in r.after for r in rewrites)
    assert any(r.before.startswith("Участвовал") for r in rewrites)


def test_recommendations_start_with_failures_and_look_ahead():
    p = analyze.parse(STRONG)
    ctx = analyze.build_context("Backend-разработчик Python", Grade.middle, None)
    recs = analyze.recommendations(analyze.run_checks(p, ctx), ctx)
    assert [r.priority for r in recs] == sorted(r.priority for r in recs)
    assert any("Senior" in r.title for r in recs)


# ---------- market ----------
def test_hh_pages_are_parsed():
    assert market.parse_search((FIXTURES / "hh_search.html").read_text()) == ["137957576", "137732636", "137765857", "137918521"]
    v = market.parse_vacancy((FIXTURES / "hh_vacancy.html").read_text(), "https://hh.kz/vacancy/1")
    assert v["title"] and v["company"] == "ТОО Пример"
    assert {"Python", "PostgreSQL", "Docker"} <= set(v["skills"])
    assert (v["salary_from"], v["salary_to"], v["currency"]) == (3000, 5000, "USD")
    assert v["experience"] == "более 6 лет" and "Kafka" in v["description"]


def _fake_hh(calls, block_after=None):
    search = (FIXTURES / "hh_search.html").read_text()
    vacancy = (FIXTURES / "hh_vacancy.html").read_text()

    def get(url):
        calls.append(url)
        if "/search/" in url:
            return search
        if block_after is not None and len(calls) > block_after + 1:
            raise market.Blocked()
        return vacancy
    return get


def test_market_sample_is_read_once_and_cached_for_a_day():
    calls = []
    items, note = market.fetch_hh("hh.kz", "Python backend", Grade.middle, "160", 3, lambda _: None,
                                  get=_fake_hh(calls), pause=(0, 0))
    assert len(items) == 3 and note == ""
    assert "experience=between1And3" in calls[0] and "experience=between3And6" in calls[0] and "area=160" in calls[0]
    again, _ = market.fetch_hh("hh.kz", "python  BACKEND", Grade.middle, "160", 3, lambda _: None,
                               get=lambda url: pytest.fail("the cache should answer"), pause=(0, 0))
    assert len(again) == 3


def test_hh_kz_is_searched_in_kazakhstan_unless_a_region_is_set():
    assert "area=40" in market.search_url("hh.kz", "Python", Grade.junior, "")
    assert "area=160" in market.search_url("hh.kz", "Python", Grade.junior, "160")
    assert "area=" not in market.search_url("hh.ru", "Python", Grade.junior, "")
    assert "experience=noExperience" in market.search_url("hh.kz", "Python", Grade.junior, "")


def test_market_cache_is_per_region():
    market.fetch_hh("hh.kz", "Python", Grade.middle, "160", 3, lambda _: None, get=_fake_hh([]), pause=(0, 0))
    calls = []
    market.fetch_hh("hh.kz", "Python", Grade.middle, "159", 3, lambda _: None, get=_fake_hh(calls), pause=(0, 0))
    assert calls  # another city: read again


def test_neighbouring_grades_keep_their_own_cache():
    # the fake hh returns the same vacancies for every grade, as overlapping experience filters do
    market.fetch_hh("hh.kz", "Python", Grade.junior, "160", 3, lambda _: None, get=_fake_hh([]), pause=(0, 0))
    market.fetch_hh("hh.kz", "Python", Grade.middle, "160", 3, lambda _: None, get=_fake_hh([]), pause=(0, 0))
    again, _ = market.fetch_hh("hh.kz", "Python", Grade.junior, "160", 3, lambda _: None,
                               get=lambda url: pytest.fail("the junior cache should survive"), pause=(0, 0))
    assert len(again) == 3


def test_captcha_keeps_what_was_read():
    items, note = market.fetch_hh("hh.kz", "Go developer", Grade.senior, "", 4, lambda _: None,
                                  get=_fake_hh([], block_after=2), pause=(0, 0))
    assert len(items) == 2 and "капч" in note


def test_market_shares_coverage_and_salary():
    base = market.parse_vacancy((FIXTURES / "hh_vacancy.html").read_text(), "u")
    items = [{**base, "url": f"u{i}", "salary_from": 1000 * (i + 1), "salary_to": None} for i in range(4)]
    items.append({**base, "url": "u9", "skills": ["Python"], "description": "", "salary_from": None, "salary_to": None})
    m = market.aggregate(items, "Python, FastAPI, PostgreSQL", "Python backend")
    shares = {s.name: s for s in m.skills}
    assert shares["Python"].share == 100 and shares["Python"].have
    assert shares["Docker"].share == 80 and not shares["Docker"].have  # 4 of 5: skill list plus the description
    assert 0 < m.coverage < 100
    assert m.salary and m.salary.currency == "USD" and m.salary.count == 4


def test_vacancies_from_other_sites_join_the_sample():
    add_vacancy(source="habr", url="https://career.habr.com/vacancies/1", title="Python-разработчик", skills="Python, Django, Docker")
    add_vacancy(source="habr", url="https://career.habr.com/vacancies/2", title="Дизайнер", skills="Figma", ext_id="2")
    rows = market.from_database("Python-разработчик")
    assert [r["url"] for r in rows] == ["https://career.habr.com/vacancies/1"] and "Docker" in rows[0]["skills"]


# ---------- AI (local model through Ollama) ----------
GOOD_ANSWER = ai._Review(
    summary="Сильный middle.", grade_fit="соответствует", grade_comment="Стаж и задачи совпадают.",
    strengths=["Цифры в опыте"], weaknesses=["Мало про архитектуру"], recommendations=["Добавьте пункт про архитектуру"],
    rewrites=[ai._Rewrite(before="Разработала REST API", after="Разработала REST API [для чего]", why="Контекст")],
)


def _fake_ollama(monkeypatch, content=None, error=None, tags=None):
    sent = []

    def request(url, body=None, timeout=ai.TIMEOUT):
        sent.append((url, body))
        if error:
            raise error
        if url.endswith("/api/tags"):
            return {"models": [{"name": n} for n in (tags or [])]}
        return {"message": {"content": GOOD_ANSWER.model_dump_json() if content is None else content}}

    monkeypatch.setattr(ai, "_request", request)
    return sent


def test_local_model_gets_checks_market_and_a_schema(monkeypatch):
    sent = _fake_ollama(monkeypatch)
    p, c = checks_of(STRONG)
    result = ai.review(STRONG, "Backend", Grade.middle, list(c.values()), None, "http://127.0.0.1:11434/", "qwen3:8b")
    assert not result.part.error and result.part.grade_fit == "соответствует" and result.part.model == "qwen3:8b"
    assert result.rewrites[0].by_ai
    url, body = sent[0]
    assert url == "http://127.0.0.1:11434/api/chat" and body["model"] == "qwen3:8b" and body["stream"] is False
    assert body["format"]["properties"]["rewrites"]  # structured output: the answer must follow the schema
    assert "Автоматические проверки" in body["messages"][1]["content"] and "<resume>" in body["messages"][1]["content"]


def test_local_model_problems_do_not_break_the_report(monkeypatch):
    _fake_ollama(monkeypatch, error=ai.OllamaError("Ollama не запущена"))
    assert "не запущена" in ai.review(STRONG, "Backend", Grade.middle, [], None, "http://x", "qwen3:8b").part.error
    _fake_ollama(monkeypatch, content="это не json")
    assert "не по формату" in ai.review(STRONG, "Backend", Grade.middle, [], None, "http://x", "qwen3:8b").part.error


def test_ollama_errors_are_explained(monkeypatch):
    import urllib.error
    import urllib.request

    def refused(*a, **k):
        raise urllib.error.URLError(ConnectionRefusedError())
    monkeypatch.setattr(urllib.request, "urlopen", refused)
    with pytest.raises(ai.OllamaError, match="ollama serve"):
        ai._request("http://127.0.0.1:11434/api/tags")

    def missing(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error": "model \'qwen3:8b\' not found"}'))
    monkeypatch.setattr(urllib.request, "urlopen", missing)
    with pytest.raises(ai.OllamaError, match="ollama pull qwen3:8b"):
        ai._request("http://127.0.0.1:11434/api/chat", {"model": "qwen3:8b"})


def test_ai_status_tells_what_to_do(monkeypatch):
    _fake_ollama(monkeypatch, tags=["qwen3:8b"])
    assert ai.status("http://127.0.0.1:11434", "qwen3:8b")["model_ready"]
    _fake_ollama(monkeypatch, tags=["llama3:8b"])
    s = ai.status("http://127.0.0.1:11434", "qwen3:8b")
    assert s["running"] and not s["model_ready"] and "ollama pull qwen3:8b" in s["message"]
    _fake_ollama(monkeypatch, tags=["qwen3:8b"])
    s = ai.status("http://127.0.0.1:11434", "qwen3")  # Ollama would look for qwen3:latest
    assert not s["model_ready"] and "qwen3:8b" in s["message"]
    _fake_ollama(monkeypatch, tags=["qwen3:latest"])
    assert ai.status("http://127.0.0.1:11434", "qwen3")["model_ready"]
    _fake_ollama(monkeypatch, error=ai.OllamaError("Ollama не запущена"))
    assert not ai.status("http://127.0.0.1:11434", "qwen3:8b")["running"]


# ---------- API ----------
@pytest.fixture
def sync_reviews(monkeypatch):
    """Run reviews in the request instead of the worker thread, without hh."""
    monkeypatch.setattr(review, "submit", lambda rid: review.run(rid, get=_fake_hh([])))
    monkeypatch.setattr(market.time, "sleep", lambda s: None)


def test_review_from_text_end_to_end(client, sync_reviews):
    r = client.post("/api/resume-reviews", data={"role": "Backend-разработчик Python", "grade": "middle", "text": STRONG,
                                                 "use_market": "true"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    d = client.get(f"/api/resume-reviews/{rid}").json()
    assert d["status"] == "done" and d["score"] == d["report"]["score"] >= 60
    assert d["report"]["role_profile"] == "Backend-разработчик"
    assert d["report"]["market"]["sample_size"] >= 3 and d["report"]["market"]["skills"]
    assert {c["group"] for c in d["report"]["checks"]} >= {"Структура", "Содержание", "Роль и грейд", "Рынок"}
    md = client.get(f"/api/resume-reviews/{rid}/export")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "# Проверка резюме: Backend-разработчик Python, Middle" in md.text
    again = client.post(f"/api/resume-reviews/{rid}/rerun").json()
    assert again["id"] != rid and again["role"] == "Backend-разработчик Python"
    assert [x["id"] for x in client.get("/api/resume-reviews").json()] == [again["id"], rid]
    assert client.delete(f"/api/resume-reviews/{rid}").status_code == 200
    assert client.get(f"/api/resume-reviews/{rid}").status_code == 404


def test_review_from_file_and_from_saved_resume(client, sync_reviews, tmp_path):
    r = client.post("/api/resume-reviews", data={"role": "Python-разработчик", "grade": "junior", "use_market": "false"},
                    files={"file": ("cv.docx", _docx(WEAK.split("\n")), "application/octet-stream")})
    assert r.status_code == 201 and r.json()["source_name"] == "cv.docx"
    saved = tmp_path / "Алия.txt"
    saved.write_text(STRONG)
    settings.save({"resume_file": str(saved)})
    r = client.post("/api/resume-reviews", data={"role": "Backend", "grade": "middle", "use_saved_file": "true",
                                                 "use_market": "false"})
    assert r.status_code == 201 and r.json()["source_name"] == "Алия.txt"
    assert client.get(f"/api/resume-reviews/{r.json()['id']}").json()["report"]["market"] is None


def test_second_review_shows_what_got_better(client, sync_reviews):
    form = {"role": "Python-разработчик", "grade": "junior", "use_market": "false"}
    first = client.post("/api/resume-reviews", data={**form, "text": WEAK}).json()["id"]
    better = WEAK.replace("Ответственный, коммуникабельный, стрессоустойчивый, быстро обучаюсь.", "Пишу бэкенд на Python.")
    better += "\nGitHub: github.com/ivanp\n"
    second = client.post("/api/resume-reviews", data={**form, "text": better}).json()["id"]
    diff = client.get(f"/api/resume-reviews/{second}").json()["report"]["diff"]
    assert diff["previous_id"] == first and diff["score_delta"] > 0
    assert "Код или портфолио" in diff["fixed"] and "Без шаблонных фраз" in diff["fixed"]
    assert diff["same_resume"] is False
    third = client.post("/api/resume-reviews", data={**form, "text": better}).json()["id"]
    assert client.get(f"/api/resume-reviews/{third}").json()["report"]["diff"]["same_resume"] is True


def test_review_input_errors(client, sync_reviews):
    assert client.post("/api/resume-reviews", data={"role": "Backend", "grade": "middle"}).status_code == 400
    assert client.post("/api/resume-reviews", data={"role": "Backend", "grade": "guru", "text": STRONG}).status_code == 422
    r = client.post("/api/resume-reviews", data={"role": "Backend", "grade": "middle", "text": STRONG, "use_ai": "true"})
    assert r.status_code == 400 and "настройках" in r.json()["detail"]  # AI is off until you switch it on


def test_ai_settings_and_review_with_the_local_model(client, sync_reviews, monkeypatch):
    assert client.patch("/api/settings", json={"ai_model": "qwen3:8b; rm -rf /"}).status_code == 422
    assert client.patch("/api/settings", json={"ollama_url": "ftp://x"}).status_code == 422
    s = client.patch("/api/settings", json={"ai_review": True, "ai_model": "qwen3:4b"}).json()
    assert s["ai_review"] and s["ai_model"] == "qwen3:4b" and s["ollama_url"] == "http://127.0.0.1:11434"
    assert client.get("/api/resume-reviews/options").json()["ai_available"] is True
    _fake_ollama(monkeypatch, tags=["qwen3:4b"])
    assert client.get("/api/resume-reviews/ai-status").json()["model_ready"] is True
    rid = client.post("/api/resume-reviews", data={"role": "Backend", "grade": "middle", "text": STRONG,
                                                   "use_market": "false", "use_ai": "true"}).json()["id"]
    report = client.get(f"/api/resume-reviews/{rid}").json()["report"]
    assert report["ai"]["used"] and report["ai"]["model"] == "qwen3:4b" and report["ai"]["summary"] == "Сильный middle."
    assert report["rewrites"][0]["by_ai"] and "Мнение ИИ" in client.get(f"/api/resume-reviews/{rid}/export").text


def test_reviews_interrupted_by_a_restart_are_marked():
    rid = reviews.create("Backend", "middle", "x", STRONG, False, False)
    review.recover()
    assert scalar("SELECT status FROM resume_reviews WHERE id=?", (rid,)) == "error"
