#!/usr/bin/env python3
"""Análise de espaço: arquivos/pastas grandes e duplicados (revisão)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

SKIP_DIR_NAMES = {
    'proc', 'sys', 'dev', 'run', 'snap',  # common system/virtual (if reached)
}
SKIP_ABS_PREFIXES = ('/proc', '/sys', '/dev', '/run')


def _should_skip_dir(path: str, root: str) -> bool:
    try:
        ap = os.path.abspath(path)
        for pref in SKIP_ABS_PREFIXES:
            if ap == pref or ap.startswith(pref + os.sep):
                return True
    except Exception:
        return True
    return False


def _iter_files(root: str, cancel=None):
    """Yield (path, size) for regular files under root, not following symlinks."""
    root = os.path.abspath(root)
    stack = [root]
    seen_dirs = set()
    while stack:
        if cancel and cancel():
            return
        current = stack.pop()
        if _should_skip_dir(current, root):
            continue
        try:
            st = os.lstat(current)
        except OSError:
            continue
        try:
            dir_key = (st.st_dev, st.st_ino)
            if dir_key in seen_dirs:
                continue
            seen_dirs.add(dir_key)
        except Exception:
            pass
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
                                size = entry.stat(follow_symlinks=False).st_size
                            except OSError:
                                continue
                            yield entry.path, int(size)
                    except OSError:
                        continue
        except OSError:
            continue


def scan_largest(root: str, top_files: int = 50, top_dirs: int = 30, cancel=None):
    """Retorna maiores arquivos e diretórios (tamanho agregado) sob root."""
    root = os.path.abspath(root)
    files = []  # (size, path)
    dir_sizes = {}
    cancelled = False

    stack = [root]
    seen_dirs = set()
    # We'll do a walk collecting file sizes and accumulating per-dir totals by walking
    # and then computing dir sizes via parent accumulation is easier in a post-pass? 
    # Simpler: record each file's size to all ancestor dirs under root.
    # To be efficient enough, collect all file records first? may be memory heavy but ok for home.
    file_records = []
    try:
        with_walk_stack = [root]
        while with_walk_stack:
            if cancel and cancel():
                cancelled = True
                break
            current = with_walk_stack.pop()
            if _should_skip_dir(current, root):
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
                                with_walk_stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                try:
                                    sz = int(entry.stat(follow_symlinks=False).st_size)
                                except OSError:
                                    continue
                                file_records.append((entry.path, sz))
                        except OSError:
                            continue
            except OSError:
                continue
            if cancelled:
                break
    except Exception:
        pass

    # largest files
    for path, sz in file_records:
        files.append({'path': path, 'size': sz})
    files.sort(key=lambda x: x['size'], reverse=True)

    # dir sizes: accumulate per directory path under root
    root_abs = root
    for path, sz in file_records:
        if cancel and cancel():
            cancelled = True
            break
        parent = os.path.dirname(path)
        # climb up to root
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


def find_duplicates(root: str, min_size: int = 1024 * 1024, top_groups: int = 50, cancel=None):
    """Encontra grupos de arquivos duplicados por conteúdo (tamanho+hash)."""
    root = os.path.abspath(root)
    by_size = {}
    cancelled = False

    # stage 1: group by size
    stack = [root]
    seen_dirs = set()
    while stack:
        if cancel and cancel():
            cancelled = True
            break
        current = stack.pop()
        if _should_skip_dir(current, root):
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
                            if sz >= min_size:
                                by_size.setdefault(sz, []).append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
        if cancelled:
            break

    groups = []
    if not cancelled:
        # stage 2: hash candidates
        candidates = [(sz, paths) for sz, paths in by_size.items() if len(paths) > 1]
        # larger potential waste first
        candidates.sort(key=lambda x: x[0] * (len(x[1]) - 1), reverse=True)
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
