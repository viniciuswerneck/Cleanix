#!/usr/bin/env python3
"""Prévias e parsing das limpezas do Otimizador (APT, Snap, Flatpak)."""

from __future__ import annotations

import re
import shutil
import subprocess

from .execution import execute_command


def _run_text(cmd, timeout=60):
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or '') + ('\n' + proc.stderr if proc.stderr else '')
        return proc.returncode == 0, out.strip()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def parse_apt_autoremove(text: str) -> dict:
    text = text or ''
    items = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^Remv\s+(\S+)', line)
        if m:
            items.append(m.group(1))
    freed_text = ''
    for line in text.splitlines():
        low = line.lower()
        if 'freed' in low or 'liberad' in low or 'espaço em disco' in low:
            freed_text = line.strip()
            break
    empty = len(items) == 0
    # also detect explicit zero-to-remove summaries
    if re.search(r'\b0\s+(to remove|a serem removidos|zu entfernen)\b', text, re.I):
        empty = True
        if not items:
            items = []
    return {'items': items, 'freed_text': freed_text, 'empty': empty}


def preview_apt_autoremove() -> dict:
    if not shutil.which('apt-get'):
        return {'available': False, 'items': [], 'freed_text': '', 'empty': True,
                'error': 'apt-get not found', 'output': ''}
    ok, output = _run_text('apt-get -s autoremove', timeout=120)
    parsed = parse_apt_autoremove(output)
    error = '' if ok else output
    # simulation often returns non-zero in some environments, but output may be valid
    if not ok and not output:
        error = 'failed'
    return {
        'available': True,
        'items': parsed['items'],
        'freed_text': parsed['freed_text'],
        'empty': parsed['empty'],
        'error': error if not parsed['items'] and not ok else '',
        'output': output,
    }


def parse_snap_disabled(text: str) -> list[dict]:
    items = []
    lines = (text or '').splitlines()
    for line in lines:
        if not line.strip():
            continue
        # skip header
        if line.lstrip().lower().startswith('name') and 'version' in line.lower():
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        notes = parts[-1]
        if 'disabled' not in notes:
            continue
        name = parts[0]
        version = parts[1]
        rev = parts[2]
        items.append({'name': name, 'version': version, 'rev': rev, 'notes': notes})
    return items


def preview_snap_disabled() -> dict:
    if not shutil.which('snap'):
        return {'available': False, 'items': [], 'error': 'snap not found'}
    ok, output = _run_text('snap list --all', timeout=60)
    items = parse_snap_disabled(output)
    return {
        'available': True,
        'items': items,
        'error': '' if ok else output,
        'output': output,
    }


def _is_flatpak_ref(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # common ref formats: org.example.App/x86_64/stable or org.example.App
    if '/' in s and '.' in s.split('/')[0]:
        return True
    if '.' in s and ' ' not in s and len(s) > 3:
        # avoid sentences
        return True
    return False


def parse_flatpak_unused(text: str) -> dict:
    text = text or ''
    low = text.lower()
    if ('nothing unused' in low or 'nada não usado' in low or 'nada nao usado' in low
            or 'nada não utilizado' in low or 'nada nao utilizado' in low):
        return {'items': [], 'empty': True, 'unparsed': False}
    items = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # skip common prompts/headings
        if s.lower().startswith(('unused runtimes', 'runtimes não usados', 'id ',
                                 'these runtimes', 'info:', 'warning:')):
            continue
        # table rows often start with number or ref
        m = re.match(r'^\d+\.\s+(\S+)', s)
        if m:
            items.append(m.group(1))
            continue
        if _is_flatpak_ref(s.split()[0] if s.split() else ''):
            items.append(s.split()[0])
            continue
    if not items and text.strip():
        # could not parse but there is content - treat as unparsed (not confidently empty)
        return {'items': [], 'empty': False, 'unparsed': True}
    return {'items': items, 'empty': len(items) == 0, 'unparsed': False}


def preview_flatpak_unused() -> dict:
    if not shutil.which('flatpak'):
        return {'available': False, 'items': [], 'empty': True, 'unparsed': False,
                'error': 'flatpak not found', 'output': ''}
    # try to get listing by answering no
    try:
        proc = subprocess.run(
            ['flatpak', 'uninstall', '--unused'],
            input='n\n', capture_output=True, text=True, timeout=60)
        output = ((proc.stdout or '') + ('\n' + proc.stderr if proc.stderr else '')).strip()
    except Exception as exc:  # noqa: BLE001
        return {'available': True, 'items': [], 'empty': True, 'unparsed': False,
                'error': str(exc), 'output': ''}
    parsed = parse_flatpak_unused(output)
    return {
        'available': True,
        'items': parsed['items'],
        'empty': parsed['empty'],
        'unparsed': parsed['unparsed'],
        'error': '',
        'output': output,
    }
