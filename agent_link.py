"""The agent's link to the cloud panel: saved token and live connection state (read by the local site)."""
import json
import os

import db

CONFIG = db.DATA_DIR / "agent.json"  # token = access to your agent: kept next to the rest of your private data
STATE = {"server": None, "email": None, "connected": False, "error": None}


def load_config():
    try:
        cfg = json.loads(CONFIG.read_text())
        return cfg if cfg.get("server") and cfg.get("token") else None
    except (OSError, ValueError):
        return None


def save_config(cfg: dict):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False))
    os.chmod(CONFIG, 0o600)


def forget():
    try:
        CONFIG.unlink()
    except FileNotFoundError:
        pass


def set_state(**kw):
    STATE.update(kw)


def public_state():
    cfg = load_config()
    return {**STATE, "paired": bool(cfg), "server": STATE["server"] or (cfg or {}).get("server"),
            "email": STATE["email"] or (cfg or {}).get("email")}
