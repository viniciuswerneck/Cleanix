#!/usr/bin/env python3
"""Histórico persistente das limpezas realizadas."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from . import i18n

MAX_ENTRIES = 200


@dataclass(frozen=True)
class HistoryEntry:
    timestamp: str
    bytes: int
    files: int
    categories: tuple[str, ...]
    errors: int


def history_path() -> Path:
    return Path.home() / ".local/share/cleanix/history.json"


def format_timestamp(iso: str) -> str:
    return i18n.format_datetime(iso)


def _entry_from_dict(data: dict) -> HistoryEntry | None:
    try:
        return HistoryEntry(
            timestamp=str(data["timestamp"]),
            bytes=int(data["bytes"]),
            files=int(data["files"]),
            categories=tuple(str(item) for item in data["categories"]),
            errors=int(data["errors"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_history(path: Path | None = None) -> list[HistoryEntry]:
    path = history_path() if path is None else Path(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []

    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []

    if not isinstance(data, list):
        return []

    entries: list[HistoryEntry] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        entry = _entry_from_dict(item)
        if entry is not None:
            entries.append(entry)
    return entries


def append_entry(entry: HistoryEntry,
                 path: Path | None = None) -> list[HistoryEntry]:
    path = history_path() if path is None else Path(path)

    entries = load_history(path=path)
    entries.append(entry)
    entries = entries[-MAX_ENTRIES:]

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = [asdict(item) for item in entries]

    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    return entries


def clear_history(path: Path | None = None) -> None:
    path = history_path() if path is None else Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass
