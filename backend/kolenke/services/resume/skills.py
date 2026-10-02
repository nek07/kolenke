"""Skill names: one canonical name per technology and its spellings, and finding skills in free text.

Employers write the same skill many ways («Postgres», «PostgreSQL», «PostgreSQL 15»), so everything is compared
through `canonical()`. The vocabulary also finds skills in vacancy descriptions that have no «Ключевые навыки»."""
import re
from collections.abc import Iterable

# canonical name → other spellings (lower case). The canonical name itself always matches.
ALIASES: dict[str, list[str]] = {
    "Python": ["питон"],
    "Java": [],
    "JavaScript": ["JS", "java script", "ecmascript", "es6"],
    "TypeScript": ["TS"],
    "Go": ["golang"],
    "PHP": [],
    "C#": ["c sharp", "csharp"],
    "C++": ["cpp"],
    "Kotlin": [],
    "Swift": [],
    "Dart": [],
    "Rust": [],
    "Ruby": [],
    "Scala": [],
    "1С": ["1c", "1с:предприятие", "1c:enterprise"],
    "SQL": ["t-sql", "pl/sql", "plsql", "tsql"],
    "PostgreSQL": ["postgres", "postgre", "psql"],
    "MySQL": [],
    "MS SQL": ["mssql", "ms sql server", "sql server", "microsoft sql server"],
    "Oracle": ["oracle db"],
    "MongoDB": ["mongo"],
    "Redis": [],
    "ClickHouse": ["clickhouse"],
    "Elasticsearch": ["elk", "opensearch"],
    "Kafka": ["apache kafka"],
    "RabbitMQ": ["rabbit mq"],
    "Celery": [],
    "Django": ["drf", "django rest framework"],
    "FastAPI": ["fast api"],
    "Flask": [],
    "Spring": ["spring boot", "spring framework"],
    "Hibernate": [],
    ".NET": ["dotnet", "asp.net", ".net core", "net core"],
    "Laravel": [],
    "Symfony": [],
    "Node.js": ["nodejs", "node js"],
    "NestJS": ["nest.js", "nest js"],
    "Express": ["express.js", "expressjs"],
    "React": ["react.js", "reactjs"],
    "Next.js": ["nextjs", "next js"],
    "Vue": ["vue.js", "vuejs", "vue 3", "nuxt"],
    "Angular": [],
    "Redux": [],
    "HTML": ["html5"],
    "CSS": ["css3", "scss", "sass"],
    "Tailwind": ["tailwindcss", "tailwind css"],
    "Webpack": ["vite"],
    "Jest": ["vitest"],
    "Flutter": [],
    "React Native": [],
    "Android": ["android sdk"],
    "iOS": ["ios sdk"],
    "SwiftUI": [],
    "Jetpack Compose": [],
    "REST": ["rest api", "restful", "restful api", "rest-api", "API"],
    "GraphQL": [],
    "gRPC": ["grpc", "protobuf"],
    "WebSocket": ["websockets", "web socket"],
    "Микросервисы": ["микросервис", "microservices", "microservice", "микросервисная архитектура"],
    "Docker": ["docker compose", "docker-compose"],
    "Kubernetes": ["k8s", "кубернетис"],
    "Helm": [],
    "Terraform": [],
    "Ansible": [],
    "CI/CD": ["ci / cd", "cicd", "ci-cd", "continuous integration"],
    "GitLab CI": ["gitlab-ci", "gitlab ci/cd"],
    "GitHub Actions": [],
    "Jenkins": [],
    "Linux": ["unix", "ubuntu", "debian", "centos"],
    "Bash": ["shell"],
    "Nginx": [],
    "AWS": ["amazon web services"],
    "GCP": ["google cloud"],
    "Azure": [],
    "Prometheus": [],
    "Grafana": [],
    "Git": ["github", "gitlab", "bitbucket"],
    "Jira": [],
    "Confluence": [],
    "Pytest": ["py.test", "unittest"],
    "Selenium": [],
    "Playwright": [],
    "Cypress": [],
    "Postman": [],
    "Unit-тесты": ["unit tests", "unit testing", "юнит-тесты", "юнит тесты", "модульные тесты", "тестирование кода"],
    "Нагрузочное тестирование": ["jmeter", "locust", "k6", "load testing"],
    "Автотесты": ["автотестирование", "автоматизированное тестирование", "test automation", "автоматизация тестирования"],
    "Тест-кейсы": ["тест-кейс", "test cases", "test case", "тестовая документация"],
    "ООП": ["oop", "объектно-ориентированное программирование"],
    "SOLID": [],
    "Паттерны проектирования": ["design patterns", "шаблоны проектирования"],
    "Алгоритмы и структуры данных": ["структуры данных", "algorithms and data structures", "data structures"],
    "Архитектура": ["system design", "архитектура приложений", "проектирование архитектуры", "software architecture"],
    "Highload": ["high load", "высоконагруженные", "высокие нагрузки", "high-load"],
    "Agile": ["scrum", "kanban", "канбан", "скрам"],
    "Pandas": [],
    "NumPy": ["numpy"],
    "Scikit-learn": ["sklearn", "scikit learn"],
    "PyTorch": [],
    "TensorFlow": ["keras"],
    "Machine Learning": ["машинное обучение", "ML"],
    "Deep Learning": ["глубокое обучение", "нейронные сети", "нейросети"],
    "Computer Vision": ["компьютерное зрение", "opencv"],
    "NLP": ["обработка естественного языка", "natural language processing"],
    "LLM": ["large language models", "GPT", "RAG", "langchain"],
    "MLOps": ["mlflow", "kubeflow"],
    "Airflow": ["apache airflow"],
    "Spark": ["pyspark", "apache spark"],
    "Hadoop": [],
    "ETL": ["elt"],
    "DWH": ["хранилище данных", "data warehouse"],
    "Статистика": ["математическая статистика", "statistics", "теория вероятностей"],
    "A/B-тесты": ["a/b тесты", "a/b testing", "a/b тестирование", "ab-тесты", "ab тесты"],
    "Excel": ["ms excel", "google sheets", "гугл таблицы"],
    "Power BI": ["powerbi"],
    "Tableau": [],
    "BPMN": [],
    "UML": [],
    "Figma": ["фигма"],
    "Английский": ["english", "английский язык"],
    "Сбор требований": ["анализ требований", "бизнес-требования", "requirements gathering", "работа с требованиями"],
    "Swagger": ["openapi"],
}

_BY_SPELLING: dict[str, str] = {}
for _name, _spellings in ALIASES.items():
    for _s in [_name.lower(), *_spellings]:
        _BY_SPELLING.setdefault(_s, _name)

_STRIP_VERSION = re.compile(r"\s+v?\d+(\.\d+)*\s*$")


def canonical(skill: str) -> str:
    """«PostgreSQL 15» → «PostgreSQL», «k8s» → «Kubernetes», «Английский — B1 — Средний» → «Английский»;
    unknown skills keep their own spelling, trimmed."""
    s = re.split(r"\s+[—–-]\s+", re.sub(r"\s+", " ", (skill or "").strip()))[0]
    key = _STRIP_VERSION.sub("", s.lower().replace("ё", "е"))
    return _BY_SPELLING.get(key) or _BY_SPELLING.get(s.lower()) or s


def _pattern(spelling: str) -> re.Pattern:
    """A whole-word match that also works for C++, C#, .NET, Node.js, CI/CD."""
    body = re.escape(spelling).replace(r"\ ", r"[\s\-]*")
    return re.compile(rf"(?<![\w+#.]){body}(?![\w+#])", re.IGNORECASE)


# short words, or words with an everyday meaning: only the exact spelling counts (Go but not «go», Express not «express»)
_EXACT = {"go", "r", "c", "express", "swift", "rust", "dart", "spring"}


def _matchers(name: str) -> list[tuple[re.Pattern, bool]]:
    out = []
    for s in [name, *ALIASES.get(name, [])]:
        exact = s.lower() in _EXACT or len(s) <= 3 and s.isupper()
        out.append((re.compile(rf"(?<![\w+#.]){re.escape(s)}(?![\w+#])") if exact else _pattern(s), exact))
    return out


_cache: dict[str, list[tuple[re.Pattern, bool]]] = {}


def mentions(text: str, skill: str) -> bool:
    """True when the text mentions the skill in any known spelling."""
    name = canonical(skill)
    if name not in _cache:
        _cache[name] = _matchers(name)
    return any(p.search(text) for p, _ in _cache[name])


# too general to be advice («добавьте JSON в резюме»), or soft skills that a resume shows by its content, not a list
GENERIC = {"json", "http", "https", "xml", "ооп", "пк", "пользователь пк", "работа в команде", "командная работа",
           "грамотная речь", "деловая коммуникация", "деловое общение", "аналитическое мышление", "ответственность",
           "коммуникабельность", "обучаемость", "самоорганизация", "тайм-менеджмент", "умение работать в команде",
           "ориентация на результат", "стрессоустойчивость", "грамотность", "внимательность", "многозадачность",
           "навыки презентации", "переговоры", "ведение переговоров", "клиентоориентированность", "it", "internet"}


def is_generic(skill: str) -> bool:
    return canonical(skill).lower() in GENERIC


# knowing the specific thing shows the general one: PostgreSQL in a resume answers «SQL» in a vacancy
IMPLIED_BY: dict[str, tuple[str, ...]] = {
    "SQL": ("PostgreSQL", "MySQL", "MS SQL", "Oracle", "ClickHouse"),
    "Git": ("GitLab CI", "GitHub Actions"),
    "CI/CD": ("GitLab CI", "GitHub Actions", "Jenkins"),
    "JavaScript": ("TypeScript", "React", "Vue", "Angular", "Node.js"),
    "Docker": ("Kubernetes",),
    "Machine Learning": ("Scikit-learn", "PyTorch", "TensorFlow", "Deep Learning"),
    "Unit-тесты": ("Pytest", "Jest"),
    "Автотесты": ("Selenium", "Playwright", "Cypress"),
}


def covers(text: str, skill: str) -> bool:
    """The text shows the skill itself or something more specific that implies it."""
    name = canonical(skill)
    return mentions(text, name) or any(mentions(text, s) for s in IMPLIED_BY.get(name, ()))


def find_in(text: str, vocabulary: Iterable[str] | None = None) -> list[str]:
    """Canonical skills mentioned in the text, from the built-in vocabulary plus any extra names."""
    names = dict.fromkeys([*ALIASES, *(canonical(v) for v in (vocabulary or []))])
    return [n for n in names if mentions(text, n)]
