#!/usr/bin/env python3
"""Armazenamento e comparação de snapshots do Raio-X."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

MAX_SNAPSHOTS = 50


def snapshots_dir() -> Path:
    base = os.environ.get('XDG_DATA_HOME')
    root = Path(base) if base else Path.home() / '.local/share'
    return root / 'cleanix' / 'snapshots'


def save_snapshot(data: dict, directory: str | Path | None = None,
                  keep: int = MAX_SNAPSHOTS) -> Path:
    directory = Path(directory) if directory is not None else snapshots_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path = directory / f'raiox-{stamp}.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)
    _prune(directory, keep=keep)
    return path


def _prune(directory: Path, keep: int = MAX_SNAPSHOTS) -> None:
    try:
        files = sorted(directory.glob('raiox-*.json'))
    except OSError:
        return
    if len(files) <= keep:
        return
    for old in files[: len(files) - keep]:
        try:
            old.unlink()
        except OSError:
            pass


def list_snapshots(directory: str | Path | None = None) -> list[dict]:
    directory = Path(directory) if directory is not None else snapshots_dir()
    try:
        files = sorted(directory.glob('raiox-*.json'), reverse=True)
    except OSError:
        return []
    items = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        meta = data.get('meta') or {}
        items.append({
            'path': str(path),
            'generated': meta.get('generated') or '',
            'os': meta.get('os') or '',
            'product': meta.get('product') or '',
            'redacted': bool(meta.get('redacted', True)),
        })
    return items


def load_snapshot(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _prog_map(items):
    out = {}
    for item in items or []:
        if isinstance(item, dict):
            name = item.get('name') or ''
            version = item.get('version') or ''
        elif isinstance(item, (list, tuple)) and item:
            name = item[0] or ''
            version = item[1] if len(item) > 1 else ''
        else:
            continue
        if name:
            out[str(name)] = str(version)
    return out


def _disk_key(disk):
    return (str(disk.get('name') or ''), str(disk.get('mount_point') or ''))


def compare_snapshots(old: dict, new: dict) -> dict:
    old = old or {}
    new = new or {}
    old_prog = old.get('programs') or {}
    new_prog = new.get('programs') or {}
    origins = ('apt', 'snap', 'flatpak_apps')
    added = {o: [] for o in origins}
    removed = {o: [] for o in origins}
    changed = {o: [] for o in origins}
    for o in origins:
        om = _prog_map(old_prog.get(o))
        nm = _prog_map(new_prog.get(o))
        for name in sorted(set(nm) - set(om)):
            added[o].append(name)
        for name in sorted(set(om) - set(nm)):
            removed[o].append(name)
        for name in sorted(set(om) & set(nm)):
            if om[name] != nm[name]:
                changed[o].append({'name': name, 'old': om[name], 'new': nm[name]})

    old_disks = { _disk_key(d): d for d in (old.get('disks') or []) if isinstance(d, dict) }
    new_disks = { _disk_key(d): d for d in (new.get('disks') or []) if isinstance(d, dict) }
    disk_changes = []
    for key in sorted(set(old_disks) & set(new_disks)):
        od, nd = old_disks[key], new_disks[key]
        try:
            op = int(od.get('pct_used')) if od.get('pct_used') is not None else None
            np = int(nd.get('pct_used')) if nd.get('pct_used') is not None else None
        except (TypeError, ValueError):
            op = np = None
        if op != np:
            disk_changes.append({
                'name': key[0], 'mount': key[1],
                'old_pct': op, 'new_pct': np,
                'old_used': od.get('size_used'), 'new_used': nd.get('size_used'),
            })

    old_sys = old.get('system') or {}
    new_sys = new.get('system') or {}
    system = {
        'updates': {'old': old_sys.get('updates'), 'new': new_sys.get('updates')},
    }

    old_alerts = { (a.get('text') or '') for a in (old.get('alerts') or []) if isinstance(a, dict) }
    new_alerts = { (a.get('text') or '') for a in (new.get('alerts') or []) if isinstance(a, dict) }
    alerts = {
        'new': sorted([t for t in (new_alerts - old_alerts) if t]),
        'resolved': sorted([t for t in (old_alerts - new_alerts) if t]),
    }

    def sec_changed(key):
        os_, ns_ = old.get(key) or {}, new.get(key) or {}
        return os_.get('summary') != ns_.get('summary')

    return {
        'programs': {'added': added, 'removed': removed, 'changed': changed},
        'disks': disk_changes,
        'system': system,
        'bios': {'changed': sec_changed('bios')},
        'hardware': {'changed': sec_changed('hardware')},
        'alerts': alerts,
    }
