"""Runtime configuration from environment variables (prefix KOLENKE_), e.g. KOLENKE_DATA_DIR=/tmp/x."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KOLENKE_")

    # database, hh browser session, uploaded resume, screenshots: never leaves this computer
    data_dir: Path = REPO_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8765
    # autopilot and reminders loop; tests switch it off
    background: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobbot.db"

    @property
    def browser_profile_dir(self) -> Path:
        return self.data_dir / "browser_profile"

    @property
    def screens_dir(self) -> Path:
        return self.data_dir / "screens"

    @property
    def resume_dir(self) -> Path:
        return self.data_dir / "resume"


@lru_cache
def get_config() -> Config:
    return Config()


def ensure_dirs(cfg: Config) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.data_dir.chmod(0o700)  # Gmail app password and the hh session live here: not for other users of this Mac
    for d in (cfg.screens_dir, cfg.resume_dir):
        d.mkdir(exist_ok=True)
