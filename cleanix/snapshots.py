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
