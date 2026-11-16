#!/usr/bin/env python3
"""Coleta de inventário da máquina (Raio-X): BIOS, hardware e programas."""

from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path

from . import systeminfo
from .execution import execute_command


DMI_KEYS = (
    'bios_vendor', 'bios_version', 'bios_date',
    'sys_vendor', 'product_name', 'product_version',
    'board_vendor', 'board_name', 'chassis_vendor',
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return ''


def read_dmi_fields(base_path: str | Path = '/sys/class/dmi/id') -> dict[str, str]:
    base = Path(base_path)
    fields: dict[str, str] = {}
    for key in DMI_KEYS:
        val = _read_text(base / key)
        if val:
            fields[key] = val
    return fields


def parse_dpkg_query(text: str) -> list[tuple[str, str]]:
    pkgs: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        version = parts[1].strip()
        status = parts[2].strip() if len(parts) > 2 else 'installed'
        if not name:
            continue
        # include only installed packages when status is provided
        if 'installed' in status or status == '' or len(parts) == 2:
            if 'config-files' in status or 'not-installed' in status:
                continue
            pkgs.append((name, version))
    return pkgs


def parse_snap_list(text: str) -> list[tuple[str, str]]:
    pkgs: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        if line.lower().startswith('name') and 'version' in line.lower():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name, version = parts[0], parts[1]
        if name.lower() == 'name':
            continue
        pkgs.append((name, version))
    return pkgs


def parse_flatpak_list(text: str) -> list[tuple[str, str]]:
    apps: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        # columns mode: id \t version ... or space separated
        if '\t' in line:
            parts = [p.strip() for p in line.split('\t')]
        else:
            parts = line.split()
        if not parts:
            continue
        name = parts[0]
        version = parts[1] if len(parts) > 1 else ''
        if name:
            apps.append((name, version))
    return apps


def parse_flatpak_runtimes_count(text: str) -> int:
    count = 0
    for line in text.splitlines():
        if line.strip():
            count += 1
    return count


def _cmd(cmd: str, timeout: int = 30) -> str:
    res = execute_command(cmd, as_root=False, timeout=timeout)
    if res.ok:
        return (res.output or '').strip()
    # sometimes tools print useful info to stdout even on nonzero; prefer stdout
    if res.output:
        return (res.output or '').strip()
    return ''


def _bios_summary(fields: dict[str, str]) -> str:
    vendor = fields.get('bios_vendor') or fields.get('sys_vendor') or 'N/D'
    ver = fields.get('bios_version') or 'N/D'
    date = fields.get('bios_date') or ''
    prod = fields.get('product_name') or fields.get('board_name') or ''
    parts = [f"BIOS: {vendor} {ver}".strip()]
    if date:
        parts.append(f"({date})")
    if prod:
        parts.append(f"- {prod}")
    return ' '.join(parts)


def _bios_details(fields: dict[str, str]) -> str:
    labels = {
        'sys_vendor': 'Fabricante do sistema',
        'product_name': 'Produto',
        'product_version': 'Versão do produto',
        'board_vendor': 'Fabricante da placa',
        'board_name': 'Placa-mãe',
        'bios_vendor': 'Fabricante da BIOS',
        'bios_version': 'Versão da BIOS',
        'bios_date': 'Data da BIOS',
        'chassis_vendor': 'Fabricante do chassi',
    }
    lines = []
    for k in DMI_KEYS:
        if k in fields:
            lines.append(f"{labels.get(k, k)}: {fields[k]}")
    try:
        u = os.uname()
        lines.append(f"Kernel: {u.release}")
        lines.append(f"Arquitetura: {u.machine}")
    except Exception:
        pass
    return '\n'.join(lines) if lines else ''


def _hardware_details() -> tuple[str, str]:
    summary_parts = []
    detail_lines = []
    limitations = []

    # CPU
    cpu_model = ''
    try:
        with open('/proc/cpuinfo', encoding='utf-8', errors='replace') as f:
            for line in f:
                if ':' in line:
                    k, v = line.split(':', 1)
                    if k.strip() in ('model name', 'Hardware', 'Processor'):
                        cpu_model = v.strip()
                        break
    except OSError:
        pass
    if shutil.which('lscpu'):
        lscpu = _cmd('lscpu')
        if lscpu:
            for line in lscpu.splitlines():
                if line.startswith('Model name:') and not cpu_model:
                    cpu_model = line.split(':', 1)[1].strip()
            detail_lines.append('== CPU (lscpu) ==')
            detail_lines.append(lscpu)
    cores = os.cpu_count() or 0
    if cpu_model or cores:
        summary_parts.append(f"CPU: {cpu_model or 'N/D'} ({cores} núcleos lógicos)")
        if not any(l.startswith('== CPU') for l in detail_lines):
            detail_lines.append('== CPU ==')
            if cpu_model:
                detail_lines.append(f"Modelo: {cpu_model}")
            detail_lines.append(f"Núcleos lógicos: {cores}")

    # Memory
    mem = systeminfo.get_mem_info()
    if mem.total:
        summary_parts.append(f"RAM: {systeminfo.format_bytes(mem.total)}")
        detail_lines.append('\n== Memória ==')
        detail_lines.append(f"Total: {systeminfo.format_bytes(mem.total)}")
        detail_lines.append(f"Disponível: {systeminfo.format_bytes(mem.available)}")

    # Disks
    try:
        disks = systeminfo._scan_disks()
        phys = [d for d in disks if d.get('type') == 'disk' and (d.get('size_total') or 0) > 0]
        if phys:
            names = ', '.join(
                f"{d.get('name')} ({systeminfo.format_bytes(d.get('size_total', 0))})" for d in phys[:4])
            summary_parts.append(f"Discos: {names}")
        if disks:
            detail_lines.append('\n== Discos/partições ==')
            for d in disks[:20]:
                t = systeminfo.format_bytes(d.get('size_total', 0))
                mp = d.get('mount_point') or ''
                detail_lines.append(f"- {d.get('name')} ({d.get('type')}): {t} {mp}".strip())
    except Exception:
        pass

    # PCI/GPU/USB
    if shutil.which('lspci'):
        lspci = _cmd('lspci -nn')
        if lspci:
            gpus = [ln for ln in lspci.splitlines()
                    if re.search(r'VGA|3D|Display', ln, re.I)]
            if gpus:
                summary_parts.append(f"GPU: {gpus[0].split(': ', 1)[-1][:60]}")
            detail_lines.append('\n== PCI ==')
            detail_lines.append(lspci)
    else:
        limitations.append('lspci indisponível')

    if shutil.which('lsusb'):
        lsusb = _cmd('lsusb')
        if lsusb:
            detail_lines.append('\n== USB ==')
            detail_lines.append(lsusb)
    else:
        limitations.append('lsusb indisponível')

    summary = ' | '.join(summary_parts) if summary_parts else 'Hardware: informações limitadas'
    details = '\n'.join(detail_lines).strip()
    if limitations:
        details += '\n\nLimitações: ' + ', '.join(limitations)
    return summary, details


def collect_unprivileged() -> dict:
    limitations: list[str] = []
    fields = read_dmi_fields()
    bios_summary = _bios_summary(fields)
    bios_details = _bios_details(fields)
    if not fields:
        limitations.append('DMI/BIOS não acessível sem privilégios ou indisponível')

    hw_summary, hw_details = _hardware_details()

    # Programs
    apt_list: list[tuple[str, str]] = []
    snap_list: list[tuple[str, str]] = []
    flatpak_apps: list[tuple[str, str]] = []
    flatpak_runtimes = 0

    if shutil.which('dpkg-query'):
        out = _cmd("dpkg-query -W -f='${Package}\\t${Version}\\t${db:Status-Status}\\n'", timeout=60)
        apt_list = parse_dpkg_query(out)
    else:
        limitations.append('dpkg-query indisponível')

    if shutil.which('snap'):
        out = _cmd('snap list', timeout=30)
        snap_list = parse_snap_list(out)
    else:
        limitations.append('snap indisponível')

    if shutil.which('flatpak'):
        out_apps = _cmd('flatpak list --app --columns=application,version', timeout=30)
        flatpak_apps = parse_flatpak_list(out_apps)
        out_rt = _cmd('flatpak list --runtime --columns=application,version', timeout=30)
        flatpak_runtimes = parse_flatpak_runtimes_count(out_rt)
    else:
        limitations.append('flatpak indisponível')

    prog_summary = (
        f"APT: {len(apt_list)} | Snap: {len(snap_list)} | "
        f"Flatpak: {len(flatpak_apps)} apps (+{flatpak_runtimes} runtimes)"
    )

    return {
        'bios': {'summary': bios_summary, 'details': bios_details, 'fields': fields},
        'hardware': {'summary': hw_summary, 'details': hw_details},
        'programs': {
            'apt': apt_list,
            'snap': snap_list,
            'flatpak_apps': flatpak_apps,
            'flatpak_runtimes': flatpak_runtimes,
            'summary': prog_summary,
        },
        'limitations': limitations,
    }


def collect_privileged_bios() -> dict:
    if not shutil.which('dmidecode'):
        return {'ok': False, 'details': '', 'source': 'dmidecode',
                'error': 'dmidecode não encontrado'}
    res = execute_command(
        'dmidecode -t bios -t system -t baseboard -t chassis',
        as_root=True, timeout=60)
    if res.ok:
        return {'ok': True, 'details': res.output or '', 'source': 'dmidecode', 'error': ''}
    return {'ok': False, 'details': res.output or '', 'source': 'dmidecode',
            'error': res.error or 'Falha ao executar dmidecode'}


def collect_privileged_hardware() -> dict:
    if not shutil.which('lshw'):
        return {'ok': False, 'details': '', 'source': 'lshw',
                'error': 'lshw não encontrado'}
    res = execute_command('lshw -short', as_root=True, timeout=90)
    if res.ok:
        return {'ok': True, 'details': res.output or '', 'source': 'lshw', 'error': ''}
    return {'ok': False, 'details': res.output or '', 'source': 'lshw',
            'error': res.error or 'Falha ao executar lshw'}
