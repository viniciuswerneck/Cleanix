#!/usr/bin/env python3
"""Lógica de lembretes de manutenção (opt-in, sem limpeza automática)."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import history


def _parse_ts(value: str):
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def last_cleanup_time(entries=None, path=None):
    entries = history.load_history(path=path) if entries is None else entries
    for entry in reversed(entries or []):
        ts = getattr(entry, 'timestamp', None)
        dt = _parse_ts(ts) if ts else None
        if dt is not None:
            return dt
    return None


def is_reminder_due(interval_days: int, enabled: bool = True, now=None,
                    entries=None, path=None) -> bool:
    if not enabled or not interval_days or interval_days <= 0:
        return False
    now = now or datetime.now()
    last = last_cleanup_time(entries=entries, path=path)
    if last is None:
        # nunca limpou: lembrar quando recurso ativo
        return True
    try:
        return (now - last) >= timedelta(days=int(interval_days))
    except Exception:
        return False
