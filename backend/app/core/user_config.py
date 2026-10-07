import json
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings

CONFIG_PATH = settings.WORKSPACE_ROOT / ".querynest_cache" / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider": "gemini",
    "model": settings.GEMINI_MODEL or "gemini-2.5-flash",
    "model_display": "Gemini 2.5 Flash",
    "mode": "normal",  # "normal" or "accept-edits"
}

AVAILABLE_MODELS = [
    {
        "id": "gemini-2.5-flash",
        "provider": "gemini",
        "name": "gemini-2.5-flash",
        "display": "Gemini 2.5 Flash",
        "desc": "Fast / Multimodal Vision / Free Tier",
    },
    {
        "id": "gemini-1.5-pro",
        "provider": "gemini",
        "name": "gemini-1.5-pro",
        "display": "Gemini 1.5 Pro",
        "desc": "Deep Reasoning / Complex Architecture",
    },
    {
        "id": "groq-llama-3.3-70b",
        "provider": "groq",
        "name": "llama-3.3-70b-versatile",
        "display": "Groq Llama 3.3 70B",
        "desc": "Ultra-Fast Code Generation",
    },
]


def get_config() -> Dict[str, Any]:
    """Loads user configuration from .querynest_cache/config.json with fallback to defaults."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(data)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Persists user configuration updates to .querynest_cache/config.json."""
    cfg = get_config()
    cfg.update(updates)
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass
    return cfg


def get_active_mode() -> str:
    """Returns the active execution mode ('normal' or 'auto')."""
    return get_config().get("mode", "normal")


def set_active_mode(mode: str) -> str:
    """Sets and persists the active execution mode ('normal' or 'accept-edits')."""
    mode = "accept-edits" if mode.lower() in ("accept-edits", "accept_edits", "auto", "accept-all", "all") else "normal"
    save_config({"mode": mode})
    return mode


def get_active_model_display() -> str:
    """Returns the display name of the currently active model."""
    cfg = get_config()
    return cfg.get("model_display") or cfg.get("model", "Gemini 2.5 Flash")


def get_active_provider() -> str:
    """Returns the active LLM provider ('gemini' or 'groq')."""
    return get_config().get("provider", "gemini")


def get_active_model_name() -> str:
    """Returns the active LLM model identifier."""
    return get_config().get("model", settings.GEMINI_MODEL)
