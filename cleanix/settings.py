"""Preferências do Cleanix, guardadas em ~/.config/cleanix/config.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from . import i18n


@dataclass(frozen=True)
class Settings:
    confirm_before_clean: bool = True
    keep_history: bool = True
    language: str = ""
    reminder_enabled: bool = False
    reminder_interval_days: int = 7


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "cleanix" / "config.json"


def load_settings(path: Path | None = None) -> Settings:
    """Lê as preferências; qualquer problema devolve os padrões."""
    path = config_path() if path is None else Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return Settings()

    if not isinstance(data, dict):
        return Settings()

    values = {}
    allowed_intervals = (7, 14, 30)
    for field, default in asdict(Settings()).items():
        value = data.get(field, default)
        if isinstance(default, bool):
            values[field] = value if isinstance(value, bool) else default
        elif isinstance(default, int) and not isinstance(default, bool):
            if isinstance(value, bool) or not isinstance(value, int):
                values[field] = default
            elif field == "reminder_interval_days":
                values[field] = value if value in allowed_intervals else default
            else:
                values[field] = value
        elif isinstance(default, str):
            if not isinstance(value, str):
                values[field] = default
            elif field == "language" and value not in ("", *i18n.LANGUAGES):
                values[field] = ""
            else:
                values[field] = value
        else:
            values[field] = default
    return Settings(**values)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = config_path() if path is None else Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n",
                    encoding="utf-8")
