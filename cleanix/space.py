#!/usr/bin/env python3
"""Análise de espaço: arquivos/pastas grandes e duplicados (revisão)."""

from __future__ import annotations

import hashlib
import os

SKIP_DIR_NAMES = {
    'proc', 'sys', 'dev', 'run', 'snap',
}
SKIP_ABS_PREFIXES = ('/proc', '/sys', '/dev', '/run')


def _should_skip_dir(path: str) -> bool:
    try:
        ap = os.path.abspath(path)
        for pref in SKIP_ABS_PREFIXES:
            if ap == pref or ap.startswith(pref + os.sep):
                return True
    except Exception:
        return True
    return False


def _emit(progress, stage, **info):
    if progress:
        try:
            progress(stage, info)
        except Exception:
            pass


def _iter_walk(root: str, cancel=None, progress=None):
    """Percorre arquivos regulares sem seguir symlinks, rendendo (path, size)."""
    root = os.path.abspath(root)
    stack = [root]
    seen_dirs = set()
    count = 0
    while stack:
        if cancel and cancel():
            return
        current = stack.pop()
        if _should_skip_dir(current):
            continue
        try:
            st = os.lstat(current)
            dir_key = (st.st_dev, st.st_ino)
            if dir_key in seen_dirs:
                continue
            seen_dirs.add(dir_key)
        except OSError:
            continue
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if cancel and cancel():
                        return
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            try:
                                sz = int(entry.stat(follow_symlinks=False).st_size)
                            except OSError:
                                continue
                            count += 1
                            if count % 200 == 0:
                                _emit(progress, 'scan', files=count)
                            yield entry.path, sz
                    except OSError:
                        continue
        except OSError:
            continue
    _emit(progress, 'scan', files=count)


def scan_largest(root: str, top_files: int = 50, top_dirs: int = 30,
                 cancel=None, progress=None):
    """Retorna maiores arquivos e diretórios (tamanho agregado) sob root."""
    root = os.path.abspath(root)
    file_records = []
    cancelled = False
    _emit(progress, 'scan', files=0)
    try:
        for path, sz in _iter_walk(root, cancel=cancel, progress=progress):
            file_records.append((path, sz))
        if cancel and cancel():
            cancelled = True
    except Exception:
        pass
    if cancel and cancel():
        cancelled = True

    files = [{'path': p, 'size': sz} for p, sz in file_records]
    files.sort(key=lambda x: x['size'], reverse=True)

    _emit(progress, 'dirs', files=len(file_records))
    dir_sizes = {}
    root_abs = root
    for path, sz in file_records:
        parent = os.path.dirname(path)
        cur = parent
        while True:
            if not (cur == root_abs or cur.startswith(root_abs + os.sep)):
                break
            dir_sizes[cur] = dir_sizes.get(cur, 0) + sz
            if cur == root_abs:
                break
            nxt = os.path.dirname(cur)
            if nxt == cur:
                break
            cur = nxt
    dirs = [{'path': p, 'size': s} for p, s in dir_sizes.items() if p != root_abs]
    dirs.sort(key=lambda x: x['size'], reverse=True)

    return {
        'files': files[:top_files],
        'dirs': dirs[:top_dirs],
        'cancelled': bool(cancelled),
        'total_files_scanned': len(file_records),
    }


def _file_hash(path: str, cancel=None):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            while True:
                if cancel and cancel():
                    return None
                chunk = f.read(1024 * 256)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def find_duplicates(root: str, min_size: int = 1024 * 1024, top_groups: int = 50,
                    cancel=None, progress=None):
    """Encontra grupos de arquivos duplicados por conteúdo (tamanho+hash)."""
    root = os.path.abspath(root)
    by_size = {}
    cancelled = False
    _emit(progress, 'scan', files=0)

    stack = [root]
    seen_dirs = set()
    count = 0
    while stack:
        if cancel and cancel():
            cancelled = True
            break
        current = stack.pop()
        if _should_skip_dir(current):
            continue
        try:
            st = os.lstat(current)
            dir_key = (st.st_dev, st.st_ino)
            if dir_key in seen_dirs:
                continue
            seen_dirs.add(dir_key)
        except OSError:
            continue
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if cancel and cancel():
                        cancelled = True
                        break
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            try:
                                sz = int(entry.stat(follow_symlinks=False).st_size)
                            except OSError:
                                continue
                            count += 1
                            if count % 200 == 0:
                                _emit(progress, 'scan', files=count)
                            if sz >= min_size:
                                by_size.setdefault(sz, []).append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
        if cancelled:
            break
    _emit(progress, 'scan', files=count)

    groups = []
    candidates = [(sz, paths) for sz, paths in by_size.items() if len(paths) > 1]
    candidates.sort(key=lambda x: x[0] * (len(x[1]) - 1), reverse=True)
    total_candidates = sum(len(p) for _, p in candidates)
    hashed = 0
    _emit(progress, 'hash', done=0, total=total_candidates, groups=0)
    for sz, paths in candidates:
        if cancel and cancel():
            cancelled = True
            break
        by_hash = {}
        for p in paths:
            if cancel and cancel():
                cancelled = True
                break
            hv = _file_hash(p, cancel=cancel)
            hashed += 1
            if hashed % 20 == 0 or hashed == total_candidates:
                _emit(progress, 'hash', done=hashed, total=total_candidates, groups=len(groups))
            if hv is None:
                if cancel and cancel():
                    cancelled = True
                continue
            by_hash.setdefault(hv, []).append(p)
        if cancelled:
            break
        for hv, same in by_hash.items():
            if len(same) > 1:
                groups.append({
                    'hash': hv,
                    'size': sz,
                    'count': len(same),
                    'wasted': sz * (len(same) - 1),
                    'files': sorted(same),
                })
    groups.sort(key=lambda g: g['wasted'], reverse=True)
    _emit(progress, 'hash', done=hashed, total=total_candidates, groups=len(groups))

    return {
        'groups': groups[:top_groups],
        'cancelled': bool(cancelled),
    }


def format_size(num_bytes):
    try:
        num = float(num_bytes)
    except Exception:
        return '0 B'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num < 1024 or unit == 'TB':
            if unit == 'B':
                return f"{int(num)} B"
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"
