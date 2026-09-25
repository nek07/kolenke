from kolenke.db.connection import query, transaction
from kolenke.schemas.settings import AppSettings


def get() -> AppSettings:
    return AppSettings.from_storage({r["key"]: r["value"] for r in query("SELECT key, value FROM settings")})


def save(values: dict) -> AppSettings:
    """Validates the merged result and stores only the given keys."""
    checked = AppSettings.model_validate({**get().model_dump(), **values})
    stored = checked.to_storage(set(values))
    with transaction() as c:
        c.executemany("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", stored.items())
    return checked
