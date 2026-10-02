"""Optional second opinion from a local model: a recruiter-style summary, grade fit and rewrites of real resume lines.

The model runs on this computer through Ollama (free, no key, the resume never leaves the Mac), Qwen by default.
The local checks and the market sample are passed along, so the model builds on them instead of guessing the market.
The answer is constrained to a JSON schema (Ollama structured outputs), then validated with Pydantic."""
import json
import urllib.error
import urllib.request

from pydantic import BaseModel, Field, ValidationError

from kolenke.schemas.enums import GRADE_LABELS, Grade
from kolenke.schemas.resume import AiPart, Check, Market, Rewrite

TIMEOUT = 600  # seconds: an 8B model on a laptop writes the review in about a minute, the first run also loads it

SYSTEM = """Ты опытный IT-рекрутер и карьерный консультант в Казахстане и СНГ. Ты разбираешь резюме кандидата под \
конкретную роль и грейд и пишешь по-русски: конкретно, доброжелательно, без воды.

Правила:
- Опирайся только на то, что написано в резюме. Не придумывай кандидату опыт, компании, технологии или цифры.
- В переписанных строках оставляй факты кандидата, а недостающие цифры и детали помечай плейсхолдерами в квадратных \
скобках, например [на сколько % ускорили]. Кандидат заполнит их сам.
- Бери для переписывания реальные строки резюме, в поле before копируй строку дословно.
- Учитывай результаты автоматических проверок и выборку вакансий: не повторяй их дословно, а объясняй, что важнее всего.
- grade_fit: одно из «соответствует», «ниже», «выше» — как резюме выглядит относительно заявленного грейда.
- Отвечай только JSON по заданной схеме."""


class _Rewrite(BaseModel):
    before: str = Field(description="Строка из резюме дословно")
    after: str = Field(description="Сильная версия строки: глагол результата, как сделано, измеримый эффект")
    why: str = Field(description="Коротко, что изменилось и почему так лучше")


class _Review(BaseModel):
    summary: str = Field(description="3–5 предложений: как резюме выглядит глазами рекрутера для этой роли и грейда")
    grade_fit: str
    grade_comment: str = Field(description="Почему такая оценка грейда, 1–2 предложения")
    strengths: list[str] = Field(description="До 5 сильных сторон")
    weaknesses: list[str] = Field(description="До 5 слабых мест, самое важное первым")
    recommendations: list[str] = Field(description="До 6 конкретных действий, самое полезное первым")
    rewrites: list[_Rewrite] = Field(description="3–6 переписанных строк опыта")


class AiResult(BaseModel):
    part: AiPart
    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[str] = []
    rewrites: list[Rewrite] = []


class OllamaError(Exception):
    """A message for you: what is wrong with the local model."""


def _prompt(text: str, role: str, grade: Grade, checks: list[Check], market: Market | None) -> str:
    lines = [f"Роль: {role}", f"Грейд: {GRADE_LABELS[grade]}", "", "Автоматические проверки:"]
    lines += [f"- [{c.status.value}] {c.title}: {c.detail}" for c in checks]
    if market and market.skills:
        lines += ["", f"Выборка вакансий ({market.sample_size} шт.), доля вакансий с навыком и есть ли он в резюме:"]
        lines += [f"- {s.name}: {s.share}% {'есть' if s.have else 'нет'}" for s in market.skills[:20]]
        if market.salary:
            s = market.salary
            lines.append(f"Зарплаты в выборке ({s.currency}): медиана {s.median}, от {s.low} до {s.high}")
    lines += ["", "Резюме:", "<resume>", text, "</resume>"]
    return "\n".join(lines)


def _request(url: str, body: dict | None = None, timeout: float = TIMEOUT) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("error", "")
        except (ValueError, AttributeError):
            pass
        if e.code == 404 and "not found" in detail:
            model = (body or {}).get("model", "")
            raise OllamaError(f"Модель {model} не скачана. В Терминале: ollama pull {model}") from e
        raise OllamaError(f"Ollama ответила ошибкой {e.code}: {detail or e.reason}") from e
    except (urllib.error.URLError, ConnectionError) as e:
        raise OllamaError("Ollama не запущена. Откройте приложение Ollama или выполните в Терминале: ollama serve") from e
    except TimeoutError as e:
        raise OllamaError("Модель не успела ответить. Попробуйте модель поменьше, например qwen3:4b") from e


def status(base_url: str, model: str) -> dict:
    """Is Ollama running and is the model downloaded: for the settings page."""
    try:
        tags = _request(f"{base_url.rstrip('/')}/api/tags", timeout=3)
    except OllamaError as e:
        return {"running": False, "model_ready": False, "models": [], "message": str(e)}
    names = [m.get("name", "") for m in tags.get("models", [])]
    # Ollama reads a name without a tag as :latest, so qwen3 is not ready when only qwen3:8b is pulled
    wanted = model if ":" in model else f"{model}:latest"
    ready = wanted in names
    if ready:
        message = "Готово: модель скачана"
    else:
        same = [n for n in names if n.split(":")[0] == model.split(":")[0]]
        message = (f"Модели {wanted} нет, но скачана {same[0]}: укажите её в настройках" if same
                   else f"Ollama работает, но модели нет. В Терминале: ollama pull {model}")
    return {"running": True, "model_ready": ready, "models": names, "message": message}


def review(text: str, role: str, grade: Grade, checks: list[Check], market: Market | None, base_url: str, model: str) -> AiResult:
    """Never raises: a failure is returned in part.error and the report stays useful without it."""
    part = AiPart(used=True, model=model)
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": _prompt(text, role, grade, checks, market)}],
        "format": _Review.model_json_schema(),  # the answer must match the schema
        "stream": False,
        "think": False,  # Qwen3 reasoning mode only slows this task down
        "options": {"temperature": 0.3, "num_ctx": 16384},
    }
    try:
        answer = _request(f"{base_url.rstrip('/')}/api/chat", body)
        r = _Review.model_validate_json(answer.get("message", {}).get("content", ""))
    except OllamaError as e:
        return AiResult(part=part.model_copy(update={"error": str(e)}))
    except ValidationError:
        return AiResult(part=part.model_copy(update={"error": "Модель ответила не по формату, попробуйте ещё раз"}))
    return AiResult(
        part=part.model_copy(update={"summary": r.summary, "grade_fit": r.grade_fit, "grade_comment": r.grade_comment}),
        strengths=r.strengths[:5], weaknesses=r.weaknesses[:5], recommendations=r.recommendations[:6],
        rewrites=[Rewrite(before=w.before, after=w.after, why=w.why, by_ai=True) for w in r.rewrites[:6]],
    )
