#!/usr/bin/env python3
"""Leitura de dados reais do sistema: disco, memória e CPU."""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import i18n

UNITS = ("B", "KB", "MB", "GB", "TB")


@dataclass(frozen=True)
class DiskInfo:
    total: int
    used: int
    free: int
    percent_used: float


@dataclass(frozen=True)
class MemInfo:
    total: int
    used: int
    available: int
    percent_used: float


def _format_number(value: float, decimals: int) -> str:
    """Formata número no separador do idioma escolhido."""
    return i18n.format_number(value, decimals)


def format_bytes(n: int) -> str:
    """Converte bytes para texto legível em pt-BR."""
    if n < 1024:
        return f"{int(n)} B"

    value = float(n)
    index = 0
    while value >= 1024 and index < len(UNITS) - 1:
        value /= 1024
        index += 1

    if value < 10:
        decimals = 2
    elif value < 100:
        decimals = 1
    else:
        decimals = 0

    return f"{_format_number(value, decimals)} {UNITS[index]}"


def format_percent(value: float, decimals: int = 0) -> str:
    return f"{_format_number(value, decimals)}%"


def _read_os_release(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text = handle.read()
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, raw = line.split('=', 1)
        values[key.strip()] = raw.strip().strip('"')
    return values


def distro_info(path: str = '/etc/os-release') -> tuple[str, str]:
    """Nome curto e versão da distribuição (para o rodapé)."""
    values = _read_os_release(path)
    name = values.get('NAME') or 'Linux'
    version = values.get('VERSION_ID', '')
    return name, version


def distro_name(path: str = '/etc/os-release') -> str:
    """Nome completo da distribuição (PRETTY_NAME quando existe)."""
    values = _read_os_release(path)
    pretty = values.get('PRETTY_NAME')
    if pretty:
        return pretty
    name = values.get('NAME') or 'Linux'
    version = values.get('VERSION_ID', '')
    return f'{name} {version}'.strip()


def get_disk_info(path: str = "/") -> DiskInfo:
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bavail * stat.f_frsize
    used = total - free
    percent = (100.0 * used / total) if total else 0.0
    return DiskInfo(total=total, used=used, free=free, percent_used=percent)


def parse_meminfo(text: str) -> MemInfo:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.split()
        if not parts:
            continue
        try:
            values[key.strip()] = int(parts[0]) * 1024
        except ValueError:
            continue

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    used = max(0, total - available)
    percent = (100.0 * used / total) if total else 0.0
    return MemInfo(total=total, used=used, available=available,
                   percent_used=percent)


def get_mem_info() -> MemInfo:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            return parse_meminfo(fh.read())
    except OSError:
        return MemInfo(total=0, used=0, available=0, percent_used=0.0)


def parse_cpu_times(text: str) -> tuple[int, int]:
    """Retorna (tempo ocupado, tempo total) da linha agregada ``cpu``."""
    for line in text.splitlines():
        if not line.startswith("cpu "):
            continue
        try:
            fields = [int(part) for part in line.split()[1:]]
        except ValueError:
            return (0, 0)
        if len(fields) < 4:
            return (0, 0)
        total = sum(fields)
        idle = fields[3]
        iowait = fields[4] if len(fields) > 4 else 0
        return (total - idle - iowait, total)
    return (0, 0)


def read_cpu_times() -> tuple[int, int]:
    try:
        with open("/proc/stat", encoding="utf-8") as fh:
            return parse_cpu_times(fh.read())
    except OSError:
        return (0, 0)


def sample_cpu(prev: tuple[int, int] | None) -> tuple[float, tuple[int, int]]:
    current = read_cpu_times()
    if prev is None:
        return (0.0, current)

    busy_delta = current[0] - prev[0]
    total_delta = current[1] - prev[1]
    if total_delta <= 0:
        return (0.0, current)

    percent = 100.0 * busy_delta / total_delta
    return (max(0.0, min(100.0, percent)), current)


def health_state(percent_free: float) -> str:
    if percent_free >= 20:
        return "ok"
    if percent_free >= 10:
        return "warn"
    return "bad"
