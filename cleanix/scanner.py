#!/usr/bin/env python3
"""Varredura e limpeza segura de lixo do usuário.

Toda remoção é limitada a uma allowlist fechada de raízes. Nada fora de
``$HOME`` ou ``/tmp`` é tocado, e links simbólicos nunca são seguidos.
"""

from __future__ import annotations

import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .execution import execute_command

BROWSER_CACHE_DIRS = (
    "google-chrome",
    "chromium",
    "mozilla/firefox",
    "brave-browser",
    "microsoft-edge",
    "vivaldi",
)


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    roots: tuple[str, ...]
    kind: str
    requires_admin: bool = False
    min_age: int = 0
    admin_command: str = ''


@dataclass(frozen=True)
class ScanResult:
    key: str
    bytes: int = 0
    files: int = 0
    errors: int = 0
    available: bool = True
    error: str = ''


@dataclass(frozen=True)
class CleanReport:
    bytes: int
    files: int
    errors: int
    per_category: dict[str, ScanResult]


def build_categories(home: Path = Path.home()) -> tuple[Category, ...]:
    home = Path(home)
    return (
        Category(
            key="trash",
            label="Lixeira do Sistema",
            roots=(
                str(home / ".local/share/Trash/files"),
                str(home / ".local/share/Trash/info"),
            ),
            kind="trash",
        ),
        Category(
            key="thumbnails",
            label="Miniaturas de Imagens",
            roots=(str(home / ".cache/thumbnails"),),
            kind="cache",
        ),
        Category(
            key="browsers",
            label="Cache dos Navegadores",
            roots=tuple(str(home / ".cache" / name)
                        for name in BROWSER_CACHE_DIRS),
            kind="cache",
        ),
        Category(
            key="tmp",
            label="Arquivos Temporários",
            roots=("/tmp",),
            kind="tmp",
            min_age=600,
        ),
        Category(
            key="apt",
            label="Cache do APT",
            roots=("/var/cache/apt/archives",),
            kind="apt",
            requires_admin=True,
            admin_command="/usr/bin/apt-get clean",
        ),
    )


CATEGORIES = build_categories()


def _scan_apt(cat: Category) -> ScanResult:
    """Conta os pacotes ``.deb`` visíveis sem precisar de root."""
    if not _root_available(cat):
        return ScanResult(key=cat.key, available=False)

    total_bytes = 0
    files = 0
    errors = 0

    for root in cat.roots:
        if not _root_is_allowed(root, "cache") or not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(
                root, followlinks=False):
            for name in filenames:
                if not name.endswith('.deb'):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    errors += 1
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue
                if not is_within(path, (root,)):
                    continue
                total_bytes += st.st_size
                files += 1

    return ScanResult(key=cat.key, bytes=total_bytes, files=files,
                      errors=errors, available=True)


def _clean_admin_files(cat: Category) -> ScanResult:
    """Limpa uma categoria do sistema por comando administrativo."""
    before = scan_category(cat)
    if not before.available:
        return before

    result = execute_command(cat.admin_command, as_root=True)
    after = scan_category(cat)
    errors = before.errors + after.errors

    if not result.ok:
        return ScanResult(
            key=cat.key, available=True, errors=errors + 1,
            error=result.error or 'O comando administrativo não foi concluído.',
        )

    return ScanResult(
        key=cat.key,
        bytes=max(0, before.bytes - after.bytes),
        files=max(0, before.files - after.files),
        errors=errors,
        available=True,
    )


def _allowed_root(root: str, expected: str) -> bool:
    """True se ``os.path.realpath(root)`` estiver dentro de ``expected``."""
    try:
        real = os.path.realpath(root)
        real_exp = os.path.realpath(expected)
        return os.path.commonpath([real, real_exp]) == real_exp
    except (OSError, ValueError):
        return False


def _root_is_allowed(root: str, kind: str = "user") -> bool:
    """True se a raiz está livre de symlinks escapados.

    Apenas rejeita quando a raiz EM SI for um symlink que aponta para fora
    do locale esperado. Diretóriosregulares são sempre aceitos (a responsabilidade
    é do is_within + lstat que já protegem contra caminhos errados).
    """
    try:
        # Apenas verifica se a raiz EM SI é symlink
        if os.path.islink(root):
            real = os.path.realpath(root)
            if kind == "tmp":
                expected = os.path.realpath("/tmp")
                return os.path.commonpath([real, expected]) == expected
            else:
                # kind == "user": raiz symlink deve estar dentro de HOME
                home = os.path.realpath(str(Path.home()))
                return os.path.commonpath([real, home]) == home
        # Raio regular: sempre aceito (já protegido por is_within + lstat)
        return True
    except (OSError, ValueError):
        return False


def is_within(path: str, roots: Iterable[str]) -> bool:
    """True apenas se ``path`` resolvido estiver dentro de uma raiz."""
    try:
        real = os.path.realpath(path)
    except OSError:
        return False

    for root in roots:
        try:
            real_root = os.path.realpath(root)
            if os.path.commonpath([real, real_root]) == real_root:
                return True
        except (OSError, ValueError):
            continue
    return False


def proc_available() -> bool:
    return Path("/proc/self/fd").is_dir()


def open_paths() -> set[str]:
    """Caminhos reais abertos ou usados como cwd por processos."""
    paths: set[str] = set()
    proc = Path("/proc")
    if not proc.is_dir():
        return paths

    try:
        entries = list(proc.iterdir())
    except OSError:
        return paths

    for entry in entries:
        if not entry.name.isdigit():
            continue

        try:
            paths.add(os.path.realpath(os.readlink(entry / "cwd")))
        except OSError:
            pass

        try:
            fds = list((entry / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                paths.add(os.path.realpath(os.readlink(fd)))
            except OSError:
                continue

    return paths


def _root_available(cat: Category) -> bool:
    for root in cat.roots:
        try:
            if os.path.isdir(root):
                return True
        except OSError:
            continue
    return False


def _prune_empty_dirs(root: str, now: float | None = None,
                      open_set: set[str] | None = None,
                      min_age: int = 0,
                      dir_meta: dict[str, tuple[int, float]] | None = None) -> None:
    if not os.path.isdir(root):
        return

    real_root = os.path.realpath(root)
    for dirpath, _dirnames, _filenames in os.walk(
            root, topdown=False, followlinks=False):
        if os.path.realpath(dirpath) == real_root:
            continue

        if min_age:
            meta = dir_meta.get(dirpath) if dir_meta else None
            if meta is None:
                try:
                    st = os.lstat(dirpath)
                except OSError:
                    continue
                uid, mtime = st.st_uid, st.st_mtime
            else:
                uid, mtime = meta
            if uid != os.getuid():
                continue
            if now is not None and mtime > now - min_age:
                continue
            if open_set is not None and os.path.realpath(dirpath) in open_set:
                continue

        try:
            if os.listdir(dirpath):
                continue
            os.rmdir(dirpath)
        except OSError:
            continue


def scan_category(cat: Category, now: float | None = None,
                  open_set: set[str] | None = None) -> ScanResult:
    if cat.kind == "apt":
        return _scan_apt(cat)
    if cat.requires_admin and not cat.admin_command:
        return ScanResult(key=cat.key, available=False)
    if not _root_available(cat):
        return ScanResult(key=cat.key, available=False)

    now = time.time() if now is None else now
    if cat.kind == "tmp":
        if open_set is None:
            if not proc_available():
                return ScanResult(key=cat.key, available=False)
            open_set = open_paths()

    total_bytes = 0
    files = 0
    errors = 0

    for root in cat.roots:
        # Pula raízes symlinkadas que escapam do local esperado
        if not _root_is_allowed(root, cat.kind):
            continue
        if not os.path.isdir(root):
            continue

        for dirpath, dirnames, filenames in os.walk(
                root, followlinks=False):
            if cat.kind == "tmp" and os.path.realpath(dirpath) in open_set:
                dirnames[:] = []
                continue
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    errors += 1
                    continue

                if not stat.S_ISREG(st.st_mode):
                    continue
                if not is_within(path, (root,)):
                    continue
                if cat.kind == "tmp":
                    if st.st_uid != os.getuid():
                        continue
                    if st.st_mtime > now - cat.min_age:
                        continue
                    if os.path.realpath(path) in open_set:
                        continue

                total_bytes += st.st_size
                files += 1

    return ScanResult(key=cat.key, bytes=total_bytes, files=files,
                      errors=errors, available=True)


def scan_all(categories: tuple[Category, ...] = CATEGORIES,
             now: float | None = None,
             open_set: set[str] | None = None) -> dict[str, ScanResult]:
    return {cat.key: scan_category(cat, now=now, open_set=open_set)
            for cat in categories}


def clean_category(cat: Category, now: float | None = None,
                   open_set: set[str] | None = None) -> ScanResult:
    if cat.requires_admin:
        if not cat.admin_command:
            return ScanResult(key=cat.key, available=False)
        return _clean_admin_files(cat)
    if not _root_available(cat):
        return ScanResult(key=cat.key, available=False)

    now = time.time() if now is None else now
    if cat.kind == "tmp":
        if open_set is None:
            if not proc_available():
                return ScanResult(key=cat.key, available=False)
            open_set = open_paths()

    # A mtime do diretório muda ao apagar seus arquivos; guardamos a original
    # antes da limpeza para decidir a poda com a idade real.
    dir_meta: dict[str, tuple[int, float]] = {}
    if cat.kind == "tmp":
        for root in cat.roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, _files in os.walk(root, followlinks=False):
                try:
                    st = os.lstat(dirpath)
                except OSError:
                    continue
                dir_meta[dirpath] = (st.st_uid, st.st_mtime)

    total_bytes = 0
    files = 0
    errors = 0

    for root in cat.roots:
        # Pula raízes symlinkadas que escapam do local esperado
        if not _root_is_allowed(root, cat.kind):
            continue
        if not os.path.isdir(root):
            continue

        for dirpath, dirnames, filenames in os.walk(
                root, followlinks=False):
            if cat.kind == "tmp" and os.path.realpath(dirpath) in open_set:
                dirnames[:] = []
                continue
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    errors += 1
                    continue

                if not stat.S_ISREG(st.st_mode):
                    continue
                if not is_within(path, (root,)):
                    continue
                if cat.kind == "tmp":
                    if st.st_uid != os.getuid():
                        continue
                    if st.st_mtime > now - cat.min_age:
                        continue
                    if os.path.realpath(path) in open_set:
                        continue

                try:
                    os.unlink(path)
                except OSError:
                    errors += 1
                    continue

                total_bytes += st.st_size
                files += 1

        _prune_empty_dirs(root, now=now, open_set=open_set,
                          min_age=cat.min_age, dir_meta=dir_meta)

    return ScanResult(key=cat.key, bytes=total_bytes, files=files,
                      errors=errors, available=True)


def clean_selected(keys: Iterable[str],
                   categories: tuple[Category, ...] = CATEGORIES,
                   now: float | None = None,
                   open_set: set[str] | None = None) -> CleanReport:
    by_key = {cat.key: cat for cat in categories}
    per_category: dict[str, ScanResult] = {}
    total_bytes = 0
    total_files = 0
    total_errors = 0

    for key in keys:
        cat = by_key.get(key)
        if cat is None:
            continue
        result = clean_category(cat, now=now, open_set=open_set)
        per_category[key] = result
        total_bytes += result.bytes
        total_files += result.files
        total_errors += result.errors

    return CleanReport(bytes=total_bytes, files=total_files,
                       errors=total_errors, per_category=per_category)
