"""What a role and a grade are expected to show in a resume. The market comparison adds the live picture on top;
these profiles make the review useful even offline and for roles with few vacancies."""
from dataclasses import dataclass, field

from kolenke.schemas.enums import Experience, Grade
from kolenke.services.text import norm


@dataclass(frozen=True)
class GradeSpec:
    months: tuple[int, int | None]  # expected commercial experience, [min, max)
    hh_experience: tuple[Experience, ...]  # hh filter for the market sample
    signals: tuple[str, ...]  # word stems that show this level of work
    words: tuple[int, int]  # a comfortable resume length in words


GRADES: dict[Grade, GradeSpec] = {
    Grade.intern: GradeSpec((0, 12), (Experience.no_experience,),
                            ("проект", "pet-проект", "pet проект", "стажиров", "курс", "обучени", "хакатон", "github", "учебн", "диплом"), (120, 600)),
    Grade.junior: GradeSpec((0, 24), (Experience.no_experience, Experience.between_1_and_3),
                            ("проект", "pet-проект", "pet проект", "стажиров", "курс", "github", "разработал", "реализовал", "исправ", "сделал"),
                            (150, 700)),
    Grade.middle: GradeSpec((18, 72), (Experience.between_1_and_3, Experience.between_3_and_6),
                            ("самостоятельно", "внедрил", "оптимизир", "автоматизир", "тест", "ревью", "ci/cd", "интеграц",
                             "с нуля", "рефактор", "ускорил", "снизил"), (250, 1000)),
    Grade.senior: GradeSpec((48, None), (Experience.between_3_and_6, Experience.more_than_6),
                            ("архитектур", "спроектировал", "проектирован", "ментор", "наставни", "code review", "ревью",
                             "highload", "нагрузк", "масштабир", "технических решени", "стандарт", "лидировал", "инициировал"),
                            (300, 1300)),
    Grade.lead: GradeSpec((72, None), (Experience.more_than_6,),
                          ("руковод", "команд", "лид", "найм", "собеседован", "управлял", "стратеги", "roadmap", "бюджет",
                           "процесс", "архитектур", "ментор"), (300, 1400)),
}


@dataclass(frozen=True)
class Requirement:
    """A must-have of the role: any of the skills counts (e.g. PostgreSQL or MySQL for «реляционная база»)."""
    title: str
    any_of: tuple[str, ...]
    from_grade: Grade = Grade.intern


@dataclass(frozen=True)
class RoleProfile:
    key: str
    label: str
    keywords: tuple[str, ...]  # stems of the role itself in the title: «backend», «тестиров»
    requirements: tuple[Requirement, ...] = field(default_factory=tuple)
    wants_portfolio: bool = True  # GitHub, Behance or a portfolio link is expected
    hints: tuple[str, ...] = ()  # technologies that suggest the role when no role word is there: «python» → backend


R = Requirement
M, S = Grade.middle, Grade.senior

ROLES: tuple[RoleProfile, ...] = (
    RoleProfile("backend", "Backend-разработчик",
                ("backend", "бэкенд", "бекенд", "back-end", "серверн", "разработчик", "developer", "программист", "engineer"),
                (R("Язык бэкенда", ("Python", "Java", "Go", "PHP", "C#", "Node.js", "Kotlin", "Ruby", "Scala", "Rust")),
                 R("SQL и реляционная база", ("SQL", "PostgreSQL", "MySQL", "MS SQL", "Oracle")),
                 R("REST API", ("REST", "GraphQL", "gRPC")),
                 R("Git", ("Git",)),
                 R("Docker", ("Docker",)),
                 R("Тесты", ("Unit-тесты", "Pytest", "Jest")),
                 R("Linux", ("Linux", "Bash"), M),
                 R("CI/CD", ("CI/CD", "GitLab CI", "GitHub Actions", "Jenkins"), M),
                 R("Кеш и очереди", ("Redis", "Kafka", "RabbitMQ", "Celery"), M),
                 R("Архитектура и микросервисы", ("Архитектура", "Микросервисы", "Highload", "Паттерны проектирования"), S),
                 R("Kubernetes", ("Kubernetes",), S)),
                hints=("python", "java", "golang", "go", "php", "django", "node", ".net", "c#", "ruby", "fastapi", "spring",
                       "laravel", "scala", "rust")),
    RoleProfile("frontend", "Frontend-разработчик",
                ("frontend", "фронтенд", "front-end", "верстальщик"),
                (R("JavaScript", ("JavaScript",)),
                 R("TypeScript", ("TypeScript",)),
                 R("HTML и CSS", ("HTML", "CSS")),
                 R("Фреймворк", ("React", "Vue", "Angular")),
                 R("Git", ("Git",)),
                 R("REST API", ("REST", "GraphQL")),
                 R("Тесты", ("Jest", "Unit-тесты", "Playwright", "Cypress"), M),
                 R("Сборка", ("Webpack",), M),
                 R("SSR и Next.js", ("Next.js",), M),
                 R("Архитектура фронтенда", ("Архитектура", "Паттерны проектирования"), S)),
                hints=("react", "vue", "angular", "javascript", "typescript", "next.js")),
    RoleProfile("fullstack", "Fullstack-разработчик",
                ("fullstack", "full-stack", "full stack", "фулстек", "фуллстек"),
                (R("Язык бэкенда", ("Python", "Java", "Go", "PHP", "C#", "Node.js")),
                 R("Фронтенд-фреймворк", ("React", "Vue", "Angular")),
                 R("TypeScript или JavaScript", ("TypeScript", "JavaScript")),
                 R("SQL", ("SQL", "PostgreSQL", "MySQL")),
                 R("REST API", ("REST", "GraphQL")),
                 R("Git", ("Git",)),
                 R("Docker", ("Docker",), M),
                 R("CI/CD", ("CI/CD", "GitLab CI", "GitHub Actions"), M))),
    RoleProfile("mobile", "Мобильный разработчик",
                ("android", "ios", "mobile", "мобильн"),
                (R("Язык", ("Kotlin", "Swift", "Dart", "Java", "JavaScript")),
                 R("Платформа", ("Android", "iOS", "Flutter", "React Native")),
                 R("REST API", ("REST", "GraphQL")),
                 R("Git", ("Git",)),
                 R("UI-фреймворк", ("SwiftUI", "Jetpack Compose", "Flutter", "React Native"), M),
                 R("Тесты", ("Unit-тесты",), M),
                 R("Архитектура", ("Архитектура", "Паттерны проектирования", "SOLID"), S)),
                hints=("flutter", "swift", "kotlin", "react native")),
    RoleProfile("qa", "QA-инженер",
                ("qa", "тестиров", "tester", "автотест", "sdet", "quality"),
                (R("Тест-кейсы и баг-репорты", ("Тест-кейсы",)),
                 R("Тестирование API", ("Postman", "REST", "Swagger")),
                 R("SQL", ("SQL", "PostgreSQL", "MySQL")),
                 R("Трекер задач", ("Jira",)),
                 R("Git", ("Git",), M),
                 R("Автотесты", ("Автотесты", "Selenium", "Playwright", "Cypress", "Pytest"), M),
                 R("CI/CD", ("CI/CD", "Jenkins", "GitLab CI"), M),
                 R("Нагрузочное тестирование", ("Нагрузочное тестирование",), S)),
                wants_portfolio=False),
    RoleProfile("devops", "DevOps-инженер",
                ("devops", "sre", "инфраструктур", "platform engineer", "системный администратор", "сисадмин"),
                (R("Linux", ("Linux",)),
                 R("Docker", ("Docker",)),
                 R("CI/CD", ("CI/CD", "GitLab CI", "GitHub Actions", "Jenkins")),
                 R("Git", ("Git",)),
                 R("Скрипты", ("Bash", "Python")),
                 R("Kubernetes", ("Kubernetes", "Helm"), M),
                 R("Инфраструктура как код", ("Terraform", "Ansible"), M),
                 R("Мониторинг", ("Prometheus", "Grafana", "Elasticsearch"), M),
                 R("Облака", ("AWS", "GCP", "Azure"), S))),
    RoleProfile("data_analyst", "Аналитик данных",
                ("аналитик данных", "data analyst", "bi-аналитик", "bi аналитик", "продуктовый аналитик", "веб-аналитик",
                 "аналитик bi"),
                (R("SQL", ("SQL", "PostgreSQL", "ClickHouse")),
                 R("Excel или таблицы", ("Excel",)),
                 R("Визуализация", ("Power BI", "Tableau")),
                 R("Python", ("Python", "Pandas")),
                 R("Статистика", ("Статистика",)),
                 R("A/B-тесты", ("A/B-тесты",), M),
                 R("ETL и хранилища", ("ETL", "DWH", "Airflow"), S)),
                wants_portfolio=False),
    RoleProfile("ml", "Data Scientist / ML-инженер",
                ("data scientist", "ml", "machine learning", "машинн", "ai", "ии", "нейросет", "deep learning",
                 "computer vision", "nlp", "llm", "data science"),
                (R("Python", ("Python",)),
                 R("Библиотеки данных", ("Pandas", "NumPy")),
                 R("Классическое ML", ("Scikit-learn", "Machine Learning")),
                 R("SQL", ("SQL", "PostgreSQL", "ClickHouse")),
                 R("Статистика", ("Статистика",)),
                 R("Нейросети", ("PyTorch", "TensorFlow", "Deep Learning"), M),
                 R("Docker", ("Docker",), M),
                 R("ML в продакшене", ("MLOps", "Airflow", "Kubernetes", "FastAPI"), S))),
    RoleProfile("analyst", "Системный / бизнес-аналитик",
                ("системный аналитик", "бизнес-аналитик", "бизнес аналитик", "business analyst", "system analyst"),
                (R("Работа с требованиями", ("Сбор требований",)),
                 R("Нотации", ("BPMN", "UML")),
                 R("SQL", ("SQL",)),
                 R("Интеграции и API", ("REST", "Swagger", "Kafka")),
                 R("Jira и Confluence", ("Jira", "Confluence"))),
                wants_portfolio=False),
    RoleProfile("manager", "Project / Product manager",
                ("project manager", "product manager", "менеджер проект", "менеджер продукт", "продакт", "product owner",
                 "руководитель проект", "проджект"),
                (R("Методологии", ("Agile",)),
                 R("Трекер задач", ("Jira", "Confluence")),
                 R("Метрики и A/B-тесты", ("A/B-тесты", "SQL", "Excel"), M)),
                wants_portfolio=False),
    RoleProfile("designer", "UX/UI-дизайнер",
                ("дизайнер", "designer", "ux", "ui/ux", "ux/ui", "product design"),
                (R("Figma", ("Figma",)),),
                wants_portfolio=True),
)

_BY_KEY = {r.key: r for r in ROLES}


def match_role(role: str) -> RoleProfile | None:
    """The profile named by the role title. A role word beats a technology («QA Python» is QA, not backend); among
    equals the longer keyword wins («системный аналитик» over «аналитик»). Generic words like «разработчик» only
    decide when nothing else matched."""
    text = f" {norm(role).replace('-', ' ')} "
    generic = {"разработчик", "developer", "программист", "engineer"}
    best, best_rank = None, (0, 0)
    for profile in ROLES:
        for kw, strength in [*((k, 2) for k in profile.keywords), *((h, 1) for h in profile.hints)]:
            k = kw.replace("-", " ")
            hit = f" {k} " in text if len(k) <= 3 else k in text
            rank = (0 if kw in generic else strength, len(k))
            if hit and rank > best_rank:
                best, best_rank = profile, rank
    return best


def by_key(key: str) -> RoleProfile | None:
    return _BY_KEY.get(key)


def grade_order(g: Grade) -> int:
    return list(Grade).index(g)
