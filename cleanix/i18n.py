#!/usr/bin/env python3
"""Traduções do Cleanix: catálogos JSON e formatação por idioma."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Mapping

log = logging.getLogger(__name__)

LANGUAGES = ('pt_BR', 'en', 'es')
LANGUAGE_NAMES = {
    'pt_BR': 'Português',
    'en': 'English',
    'es': 'Español',
}
FALLBACK = 'pt_BR'
LOCALE_DIR = Path(__file__).with_name('locale')

_current = FALLBACK


def _parse_locale(value: str) -> str | None:
    if not value:
        return None
    code = value.split('.', 1)[0].replace('-', '_')
    prefix = code.split('_', 1)[0].lower()
    if prefix == 'pt':
        return 'pt_BR'
    if prefix in ('en', 'es'):
        return prefix
    return None


def detect_language(env: Mapping[str, str] | None = None) -> str:
    """Escolhe o idioma a partir de LC_ALL, LC_MESSAGES ou LANG."""
    env = os.environ if env is None else env
    for name in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        code = _parse_locale(env.get(name, ''))
        if code is not None:
            return code
    return FALLBACK


@lru_cache(maxsize=8)
def _catalog(code: str) -> dict[str, str]:
    path = LOCALE_DIR / f'{code}.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        log.warning('Não foi possível carregar o catálogo %s: %s', code, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def catalog_keys(code: str) -> set[str]:
    return set(_catalog(code))


def set_language(code: str) -> bool:
    global _current
    if code not in LANGUAGES:
        _current = FALLBACK
        return False
    _current = code
    return True


def get_language() -> str:
    return _current


def _lookup(key: str) -> str | None:
    text = _catalog(_current).get(key)
    if text is None and _current != FALLBACK:
        text = _catalog(FALLBACK).get(key)
    if text is None:
        log.warning('Chave de tradução ausente: %s (%s)', key, _current)
    return text


def t(key: str, **values) -> str:
    text = _lookup(key)
    if text is None:
        return key
    if not values:
        return text
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        log.warning('Valores incompatíveis em %s: %r', key, values)
        return text


def tn(key: str, n: int, **values) -> str:
    suffix = 'one' if n == 1 else 'other'
    values.setdefault('n', n)
    return t(f'{key}.{suffix}', **values)


def format_number(value: float, decimals: int = 0) -> str:
    text = f'{value:,.{decimals}f}'
    if _current == 'en':
        return text
    return text.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def format_datetime(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return moment.strftime(t('date.pattern'))
