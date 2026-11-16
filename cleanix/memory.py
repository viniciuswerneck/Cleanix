#!/usr/bin/env python3
"""Liberação do cache de arquivos da memória RAM."""

from __future__ import annotations

from pathlib import Path

from . import i18n, systeminfo
from .execution import Result, execute_command

MEMINFO_PATH = Path('/proc/meminfo')
DROP_CACHES_COMMAND = 'sync && echo 3 > /proc/sys/vm/drop_caches'


def read_meminfo(path=MEMINFO_PATH) -> dict[str, int]:
    """Lê ``/proc/meminfo`` e devolve os valores em bytes."""
    values: dict[str, int] = {}
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return values

    for line in text.splitlines():
        if ':' not in line:
            continue
        key, raw = line.split(':', 1)
        parts = raw.split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        if len(parts) > 1 and parts[1].lower() == 'kb':
            value *= 1024
        values[key.strip()] = value
    return values


def reclaimable_memory(values: dict[str, int]) -> int:
    """Bytes de cache que o ``drop_caches`` consegue liberar.

    O cache de páginas e a parte reclamável do slab entram na conta; a
    memória compartilhada (tmpfs) não pode ser descartada.
    """
    cached = values.get('Cached', 0)
    slab = values.get('SReclaimable', 0)
    shmem = values.get('Shmem', 0)
    return max(0, cached + slab - shmem)


def release_memory() -> Result:
    """Descarta o cache da RAM e devolve quantos bytes foram liberados."""
    before = read_meminfo()
    if not before or 'MemAvailable' not in before:
        return Result(False, '', i18n.t('memory.read_failed'))

    result = execute_command(DROP_CACHES_COMMAND, as_root=True)
    if not result.ok:
        return result

    after = read_meminfo()
    before_available = before.get('MemAvailable', 0)
    after_available = after.get('MemAvailable', before_available)
    freed = max(0, after_available - before_available)

    if freed:
        output = i18n.t('memory.freed',
                        size=systeminfo.format_bytes(freed))
    else:
        output = i18n.t('memory.nothing_freed')
    return Result(True, output, '')
