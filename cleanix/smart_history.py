#!/usr/bin/env python3
"""Histórico persistente de verificações SMART por disco."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MAX_PER_DISK = 20
MAX_TOTAL = 200


def history_path() -> Path:
    return Path.home() / '.local/share/cleanix/smart_history.json'


def load_history(path: Path | None = None) -> list[dict]:
    path = history_path() if path is None else Path(path)
    try:
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and item.get('disk'):
            out.append(item)
    return out


def _save_history(entries: list[dict], path: Path | None = None) -> None:
    path = history_path() if path is None else Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                       encoding='utf-8')
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _critical_map(parsed: dict) -> dict[str, str]:
    out = {}
    for attr in (parsed or {}).get('attributes') or []:
        if not attr.get('critical'):
            continue
        name = attr.get('name')
        if not name:
            continue
        out[str(name)] = str(attr.get('raw', attr.get('value', '')))
    return out


def _matches(entry: dict, disk: str, model: str | None) -> bool:
    if entry.get('disk') != disk:
        return False
    if model and entry.get('model') and entry.get('model') != model:
        return False
    return True


def last_for_disk(disk: str, model: str | None = None,
                  path: Path | None = None):
    for entry in reversed(load_history(path=path)):
        if _matches(entry, disk, model):
            return entry
    return None


def _parse_raw_int(value):
    if value is None:
        return None
    text = str(value).strip().split()[0]
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def compare_previous(disk: str, model: str | None, parsed: dict,
                     path: Path | None = None):
    prev = last_for_disk(disk, model, path=path)
    if prev is None:
        return None
    messages = []
    worsened = False
    prev_overall = prev.get('overall') or 'unknown'
    cur_overall = (parsed or {}).get('overall') or 'unknown'
    if prev_overall == 'passed' and cur_overall == 'failed':
        worsened = True
        messages.append('SMART overall: PASSED -> FAILED')
    prev_crit = prev.get('critical') or {}
    cur_crit = _critical_map(parsed)
    for name, cur_raw in cur_crit.items():
        if name not in prev_crit:
            continue
        p = _parse_raw_int(prev_crit.get(name))
        c = _parse_raw_int(cur_raw)
        if p is not None and c is not None and c > p:
            worsened = True
            messages.append(f'{name}: {p} -> {c}')
    if not worsened:
        return None
    overall_worsened = prev_overall == 'passed' and cur_overall == 'failed'
    return {
        'worsened': True,
        'messages': messages,
        'overall_worsened': overall_worsened,
        'previous': prev,
    }


def record_check(disk: str, model: str | None, parsed: dict,
                 path: Path | None = None):
    if not disk:
        return load_history(path=path)
    entries = load_history(path=path)
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'disk': disk,
        'model': model or '',
        'overall': (parsed or {}).get('overall') or 'unknown',
        'overall_text': (parsed or {}).get('overall_text') or '',
        'critical': _critical_map(parsed),
    }
    entries.append(entry)
    # limit per disk
    counts = {}
    kept = []
    for item in reversed(entries):
        key = (item.get('disk'), item.get('model') or '')
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= MAX_PER_DISK:
            kept.append(item)
    kept = list(reversed(kept))[-MAX_TOTAL:]
    try:
        _save_history(kept, path=path)
    except OSError:
        pass
    return kept
