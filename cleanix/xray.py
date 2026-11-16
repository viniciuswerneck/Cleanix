#!/usr/bin/env python3
"""Coleta de inventário da máquina (Raio-X): BIOS, hardware e programas."""

from __future__ import annotations

import os
import platform
import re
import shutil
import csv
import io
import json
from datetime import datetime
from pathlib import Path

from . import i18n, systeminfo
from . import version as cleanix_version
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


_SENSITIVE_PREFIXES = (
    'serial number', 'uuid', 'sku number', 'asset tag', 'serial',
)


def redact_sensitive(text: str) -> str:
    """Mascara identificadores de hardware em saídas de dmidecode/lshw."""
    if not text:
        return ''
    hidden = i18n.t('xray.redacted')
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        matched = None
        for prefix in _SENSITIVE_PREFIXES:
            if low.startswith(prefix + ':') or low.startswith(prefix + ' :'):
                matched = prefix
                break
        if matched is None:
            lines.append(line)
            continue
        indent = line[:len(line) - len(line.lstrip())]
        label, _, _ = stripped.partition(':')
        lines.append(f"{indent}{label.strip()}: {hidden}")
    return '\n'.join(lines)


def redact_network_macs(text: str) -> str:
    """Mascara endereços MAC em textos de rede."""
    if not text:
        return ''
    hidden = i18n.t('xray.redacted')
    return re.sub(r'(?im)^(\s*MAC:\s*).*$', lambda m: m.group(1) + hidden, text)


def format_kb(kb) -> str:
    """Converte a coluna Installed-Size (KB) em texto legível."""
    try:
        value = int(str(kb).strip())
    except (TypeError, ValueError):
        return ''
    if value <= 0:
        return ''
    return systeminfo.format_bytes(value * 1024)


def read_dmi_fields(base_path: str | Path = '/sys/class/dmi/id') -> dict[str, str]:
    base = Path(base_path)
    fields: dict[str, str] = {}
    for key in DMI_KEYS:
        val = _read_text(base / key)
        if val:
            fields[key] = val
    return fields


def parse_dpkg_query(text: str) -> list[tuple[str, str, str]]:
    pkgs: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        version = parts[1].strip()
        status = parts[2].strip() if len(parts) > 2 else 'installed'
        size = format_kb(parts[3]) if len(parts) > 3 else ''
        if not name:
            continue
        # include only installed packages when status is provided
        if 'installed' in status or status == '' or len(parts) == 2:
            if 'config-files' in status or 'not-installed' in status:
                continue
            pkgs.append((name, version, size))
    return pkgs


def parse_snap_list(text: str) -> list[tuple[str, str, str]]:
    pkgs: list[tuple[str, str, str]] = []
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
        pkgs.append((name, version, ''))
    return pkgs


def parse_flatpak_list(text: str) -> list[tuple[str, str, str]]:
    apps: list[tuple[str, str, str]] = []
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
        size = parts[2] if len(parts) > 2 else ''
        if name:
            apps.append((name, version, size))
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


def parse_ip_brief(text: str) -> list[dict]:
    """Interpreta ``ip -brief addr`` em uma lista de interfaces."""
    interfaces = []
    for line in (text or '').splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        interfaces.append({
            'name': parts[0],
            'state': parts[1],
            'addresses': parts[2:],
        })
    return interfaces


def _read_mac(name: str, base_path: str | Path = '/sys/class/net') -> str:
    mac = _read_text(Path(base_path) / name / 'address')
    return mac.lower() if mac else ''


def collect_network() -> dict:
    """Coleta interfaces físicas (sem ``lo``), estado, IPs e MAC."""
    interfaces = []
    for item in parse_ip_brief(_cmd('ip -brief addr', timeout=10)):
        if item['name'] == 'lo':
            continue
        item['mac'] = _read_mac(item['name'])
        interfaces.append(item)

    if not interfaces:
        text = i18n.t('xray.network.none')
        return {'summary': text, 'details': text, 'interfaces': []}

    names = ', '.join(item['name'] for item in interfaces)
    summary = i18n.t('xray.network.summary', n=len(interfaces), names=names)
    lines = ['▸ ' + i18n.t('xray.section.network')]
    for item in interfaces:
        lines.append(f"  • {item['name']} — {item['state']}")
        if item['addresses']:
            lines.append('    IP: ' + ', '.join(item['addresses']))
        if item['mac']:
            lines.append('    MAC: ' + item['mac'])
    return {'summary': summary, 'details': '\n'.join(lines),
            'interfaces': interfaces}


def parse_uptime(text: str) -> int:
    """Lê o primeiro campo de ``/proc/uptime`` (segundos)."""
    try:
        return int(float((text or '').split()[0]))
    except (IndexError, ValueError):
        return 0


def format_uptime(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = []
    if days:
        parts.append(i18n.t('xray.uptime.days', n=days))
    if hours:
        parts.append(i18n.t('xray.uptime.hours', n=hours))
    if minutes or not parts:
        parts.append(i18n.t('xray.uptime.minutes', n=minutes))
    return ' '.join(parts)


def parse_apt_upgradable(text: str) -> int:
    """Conta pacotes na saída de ``apt list --upgradable``."""
    count = 0
    for line in (text or '').splitlines():
        low = line.lower()
        if 'upgradable from' in low and '[' in line:
            count += 1
    return count


def secure_boot_state(base_path: str | Path = '/sys/firmware/efi/efivars') -> str:
    """Devolve ``enabled``, ``disabled`` ou ``''`` conforme o efivars."""
    try:
        files = sorted(Path(base_path).glob('SecureBoot-*'))
    except OSError:
        return ''
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) >= 5:
            return 'enabled' if data[4] else 'disabled'
    return ''


def collect_system() -> dict:
    """Coleta uptime, atualizações pendentes, Secure Boot e TPM."""
    uptime = format_uptime(parse_uptime(_read_text(Path('/proc/uptime'))))
    updates = 0
    if shutil.which('apt'):
        updates = parse_apt_upgradable(
            _cmd('apt list --upgradable 2>/dev/null', timeout=20))
    secure = secure_boot_state()
    tpm = Path('/sys/class/tpm/tpm0').exists()

    if secure == 'enabled':
        secure_text = i18n.t('xray.system.enabled')
    elif secure == 'disabled':
        secure_text = i18n.t('xray.system.disabled')
    else:
        secure_text = i18n.t('xray.system.unknown')
    tpm_text = (i18n.t('xray.system.present') if tpm
                else i18n.t('xray.system.absent'))

    fields = (
        (i18n.t('xray.system.uptime'), uptime),
        (i18n.t('xray.system.updates'), updates),
        (i18n.t('xray.system.secure_boot'), secure_text),
        (i18n.t('xray.system.tpm'), tpm_text),
    )
    summary = ' | '.join(f'{label}: {value}' for label, value in fields)
    lines = ['▸ ' + i18n.t('xray.section.systeminfo')]
    lines.extend(f'  • {label}: {value}' for label, value in fields)
    return {
        'summary': summary,
        'details': '\n'.join(lines),
        'uptime': uptime,
        'updates': updates,
        'secure_boot': secure,
        'tpm': tpm,
    }


def _bios_year(value: str) -> int:
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime((value or '').strip(), fmt).year
        except (TypeError, ValueError):
            continue
    return 0


def build_alerts(bios_date: str, disk_usages, flatpak_runtimes,
                 pending_updates, now_year: int) -> list[dict]:
    """Calcula destaques locais, sem rede e sem privilégios."""
    alerts = []
    year = _bios_year(bios_date)
    if year and now_year - year > 6:
        alerts.append({
            'level': 'warn',
            'text': i18n.t('xray.alert.bios', year=year,
                           age=now_year - year),
        })

    for disk in disk_usages or []:
        try:
            pct = int(disk.get('pct_used') or 0)
        except (TypeError, ValueError):
            continue
        if pct >= 90:
            mount = disk.get('mount_point') or disk.get('name') or '?'
            alerts.append({
                'level': 'warn',
                'text': i18n.t('xray.alert.disk', mount=mount, pct=pct),
            })

    try:
        runtimes = int(flatpak_runtimes or 0)
    except (TypeError, ValueError):
        runtimes = 0
    if runtimes >= 20:
        alerts.append({
            'level': 'info',
            'text': i18n.t('xray.alert.flatpak', n=runtimes),
        })

    try:
        updates = int(pending_updates or 0)
    except (TypeError, ValueError):
        updates = 0
    if updates > 0:
        alerts.append({
            'level': 'info',
            'text': i18n.t('xray.alert.updates', n=updates),
        })
    return alerts


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
        'sys_vendor': i18n.t('xray.field.sys_vendor'),
        'product_name': i18n.t('xray.field.product_name'),
        'product_version': i18n.t('xray.field.product_version'),
        'board_vendor': i18n.t('xray.field.board_vendor'),
        'board_name': i18n.t('xray.field.board_name'),
        'bios_vendor': i18n.t('xray.field.bios_vendor'),
        'bios_version': i18n.t('xray.field.bios_version'),
        'bios_date': i18n.t('xray.field.bios_date'),
        'chassis_vendor': i18n.t('xray.field.chassis_vendor'),
    }
    sections = []
    sys_lines = []
    for k in ('sys_vendor', 'product_name', 'product_version', 'chassis_vendor'):
        if k in fields:
            sys_lines.append(f"• {labels.get(k, k)}: {fields[k]}")
    if sys_lines:
        sections.append(i18n.t('xray.section.system') + "\n" + "\n".join(sys_lines))

    board_lines = []
    for k in ('board_vendor', 'board_name'):
        if k in fields:
            board_lines.append(f"• {labels.get(k, k)}: {fields[k]}")
    if board_lines:
        sections.append(i18n.t('xray.section.motherboard') + "\n"
                        + "\n".join(board_lines))

    bios_lines = []
    for k in ('bios_vendor', 'bios_version', 'bios_date'):
        if k in fields:
            bios_lines.append(f"• {labels.get(k, k)}: {fields[k]}")
    if bios_lines:
        sections.append(i18n.t('xray.section.firmware') + "\n"
                        + "\n".join(bios_lines))

    try:
        u = os.uname()
        sections.append(
            i18n.t('xray.section.os') + "\n"
            + f"• {i18n.t('xray.field.kernel')}: {u.release}\n"
            + f"• {i18n.t('xray.field.architecture')}: {u.machine}")
    except Exception:
        pass
    return '\n\n'.join(sections) if sections else ''


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
    cores = os.cpu_count() or 0
    if cpu_model or cores:
        summary_parts.append(
            f"CPU: {cpu_model or 'N/D'} "
            f"({i18n.t('xray.summary.cores', n=cores)})")
    detail_lines.append('▸ ' + i18n.t('xray.section.cpu'))
    if cpu_model:
        detail_lines.append(f"  • {i18n.t('xray.field.model')}: {cpu_model}")
    detail_lines.append(
        f"  • {i18n.t('xray.field.logical_cores')}: {cores}")
    try:
        detail_lines.append(
            f"  • {i18n.t('xray.field.architecture')}: {platform.machine()}")
    except Exception:
        pass

    # Memory
    mem = systeminfo.get_mem_info()
    if mem.total:
        summary_parts.append(f"RAM: {systeminfo.format_bytes(mem.total)}")
    detail_lines.append('\n▸ ' + i18n.t('xray.section.memory'))
    if mem.total:
        detail_lines.append(
            f"  • {i18n.t('xray.field.total')}: "
            f"{systeminfo.format_bytes(mem.total)}")
        detail_lines.append(
            f"  • {i18n.t('xray.field.available')}: "
            f"{systeminfo.format_bytes(mem.available)}")
        detail_lines.append(
            f"  • {i18n.t('xray.field.used')}: "
            f"{systeminfo.format_bytes(mem.used)}")
    else:
        detail_lines.append('  • ' + i18n.t('xray.unavailable'))

    # Disks
    disks = []
    try:
        disks = systeminfo._scan_disks()
        phys = [d for d in disks
                if d.get('type') == 'disk' and (d.get('size_total') or 0) > 0]
        if phys:
            names = ', '.join(
                f"{d.get('name')} "
                f"({systeminfo.format_bytes(d.get('size_total', 0))})"
                for d in phys[:4])
            summary_parts.append(
                f"{i18n.t('xray.summary.disks')}: {names}")
        detail_lines.append('\n▸ ' + i18n.t('xray.section.disks'))
        if disks:
            for d in disks[:20]:
                total = systeminfo.format_bytes(d.get('size_total', 0))
                mp = d.get('mount_point') or ''
                dtype = d.get('type') or ''
                prefix = '  •' if dtype == 'disk' else '    -'
                extra = f"  [{mp}]" if mp else ''
                detail_lines.append(
                    f"{prefix} {d.get('name')} ({dtype}, {total}){extra}")
        else:
            detail_lines.append('  • ' + i18n.t('xray.unavailable'))
    except Exception:
        detail_lines.append('\n▸ ' + i18n.t('xray.section.disks'))
        detail_lines.append('  • ' + i18n.t('xray.unavailable'))

    # PCI/GPU/USB
    if shutil.which('lspci'):
        lspci = _cmd('lspci -nn')
        if lspci:
            gpus = [ln for ln in lspci.splitlines()
                    if re.search(r'VGA|3D|Display', ln, re.I)]
            if gpus:
                summary_parts.append(f"GPU: {gpus[0].split(': ', 1)[-1][:60]}")
            detail_lines.append('\n▸ ' + i18n.t('xray.section.gpu'))
            for g in gpus[:6]:
                detail_lines.append('  • ' + g.split(': ', 1)[-1])
            detail_lines.append('\n▸ ' + i18n.t('xray.section.pci'))
            pci_lines = lspci.splitlines()
            for ln in pci_lines[:40]:
                detail_lines.append('  • ' + ln)
            if len(pci_lines) > 40:
                detail_lines.append(
                    '  ' + i18n.t('xray.field.items_more',
                                  n=len(pci_lines) - 40))
    else:
        limitations.append(i18n.t('xray.error.tool_missing', tool='lspci'))
        detail_lines.append('\n▸ ' + i18n.t('xray.section.pci'))
        detail_lines.append('  • ' + i18n.t('xray.unavailable'))

    if shutil.which('lsusb'):
        lsusb = _cmd('lsusb')
        if lsusb:
            detail_lines.append('\n▸ ' + i18n.t('xray.section.usb'))
            usb_lines = lsusb.splitlines()
            for ln in usb_lines[:30]:
                detail_lines.append('  • ' + ln)
            if len(usb_lines) > 30:
                detail_lines.append(
                    '  ' + i18n.t('xray.field.items_more',
                                  n=len(usb_lines) - 30))
    else:
        limitations.append(i18n.t('xray.error.tool_missing', tool='lsusb'))

    summary = (' | '.join(summary_parts) if summary_parts
               else i18n.t('xray.summary.limited'))
    details = '\n'.join(detail_lines).strip()
    if limitations:
        details += ('\n\n⚠ ' + i18n.t('xray.field.limitations') + ': '
                    + ', '.join(limitations))
    return summary, details


def collect_unprivileged() -> dict:
    limitations: list[str] = []
    fields = read_dmi_fields()
    bios_summary = _bios_summary(fields)
    bios_details = _bios_details(fields)
    if not fields:
        limitations.append(i18n.t('xray.error.dmi'))

    hw_summary, hw_details = _hardware_details()

    # Programs
    apt_list: list[tuple[str, str]] = []
    snap_list: list[tuple[str, str]] = []
    flatpak_apps: list[tuple[str, str]] = []
    flatpak_runtimes = 0

    if shutil.which('dpkg-query'):
        out = _cmd("dpkg-query -W -f='${Package}\\t${Version}\\t${db:Status-Status}\\t${Installed-Size}\\n'", timeout=60)
        apt_list = parse_dpkg_query(out)
    else:
        limitations.append(i18n.t('xray.error.tool_missing', tool='dpkg-query'))

    if shutil.which('snap'):
        out = _cmd('snap list', timeout=30)
        snap_list = parse_snap_list(out)
    else:
        limitations.append(i18n.t('xray.error.tool_missing', tool='snap'))

    if shutil.which('flatpak'):
        out_apps = _cmd('flatpak list --app --columns=application,version,size', timeout=30)
        flatpak_apps = parse_flatpak_list(out_apps)
        out_rt = _cmd('flatpak list --runtime --columns=application,version', timeout=30)
        flatpak_runtimes = parse_flatpak_runtimes_count(out_rt)
    else:
        limitations.append(i18n.t('xray.error.tool_missing', tool='flatpak'))

    prog_summary = (
        f"APT: {len(apt_list)} | Snap: {len(snap_list)} | "
        f"Flatpak: {len(flatpak_apps)} apps (+{flatpak_runtimes} runtimes)"
    )

    network = collect_network()
    system = collect_system()

    try:
        disks = systeminfo._scan_disks()
    except Exception:
        disks = []

    alerts = build_alerts(
        fields.get('bios_date', ''), disks, flatpak_runtimes,
        system.get('updates', 0), datetime.now().year)

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
        'network': network,
        'system': system,
        'disks': disks,
        'alerts': alerts,
        'limitations': limitations,
    }


def collect_privileged_bios() -> dict:
    if not shutil.which('dmidecode'):
        return {'ok': False, 'details': '', 'source': 'dmidecode',
                'error': i18n.t('xray.error.tool_missing', tool='dmidecode')}
    res = execute_command(
        'dmidecode -t bios -t system -t baseboard -t chassis',
        as_root=True, timeout=60)
    if res.ok:
        return {'ok': True, 'details': res.output or '', 'source': 'dmidecode', 'error': ''}
    return {'ok': False, 'details': res.output or '', 'source': 'dmidecode',
            'error': res.error or i18n.t('xray.error.exec_failed', tool='dmidecode')}


def collect_privileged_hardware() -> dict:
    if not shutil.which('lshw'):
        return {'ok': False, 'details': '', 'source': 'lshw',
                'error': i18n.t('xray.error.tool_missing', tool='lshw')}
    res = execute_command('lshw -short', as_root=True, timeout=90)
    if res.ok:
        return {'ok': True, 'details': res.output or '', 'source': 'lshw', 'error': ''}
    return {'ok': False, 'details': res.output or '', 'source': 'lshw',
            'error': res.error or i18n.t('xray.error.exec_failed', tool='lshw')}


PRIV_BIOS_MARK = '__CLEANIX_XRAY_BIOS__'
PRIV_HW_MARK = '__CLEANIX_XRAY_HW__'


def collect_privileged_all() -> dict:
    """Coleta BIOS (dmidecode) e hardware (lshw) com uma única senha."""
    have_bios = bool(shutil.which('dmidecode'))
    have_hw = bool(shutil.which('lshw'))
    if not have_bios and not have_hw:
        return {
            'ok': False,
            'bios': {'ok': False, 'details': '', 'source': 'dmidecode'},
            'hardware': {'ok': False, 'details': '', 'source': 'lshw'},
            'error': i18n.t('xray.error.priv_none'),
        }
    bios_cmd = ('dmidecode -t bios -t system -t baseboard -t chassis 2>&1'
                if have_bios else 'true')
    hw_cmd = 'lshw -short 2>&1' if have_hw else 'true'
    command = (f'echo {PRIV_BIOS_MARK}; {bios_cmd}; '
               f'echo {PRIV_HW_MARK}; {hw_cmd}')
    res = execute_command(command, as_root=True, timeout=150)
    output = res.output or ''
    bios_text = ''
    hw_text = ''
    if PRIV_BIOS_MARK in output:
        rest = output.split(PRIV_BIOS_MARK, 1)[1]
        if PRIV_HW_MARK in rest:
            bios_text, hw_text = rest.split(PRIV_HW_MARK, 1)
        else:
            bios_text = rest
    elif PRIV_HW_MARK in output:
        hw_text = output.split(PRIV_HW_MARK, 1)[1]
    else:
        hw_text = output
    bios_text = bios_text.strip()
    hw_text = hw_text.strip()
    return {
        'ok': bool(res.ok),
        'bios': {
            'ok': bool(res.ok and have_bios and bios_text),
            'details': bios_text,
            'source': 'dmidecode',
        },
        'hardware': {
            'ok': bool(res.ok and have_hw and hw_text),
            'details': hw_text,
            'source': 'lshw',
        },
        'error': '' if res.ok else (
            res.error or i18n.t('xray.error.priv_failed')),
    }


def os_pretty_name() -> str:
    try:
        info = platform.freedesktop_os_release()
    except Exception:
        return ''
    return info.get('PRETTY_NAME') or info.get('NAME') or ''


_REPORT_CSS = """
:root {
    --bg: #f3f5fb;
    --card: #ffffff;
    --ink: #1c2333;
    --muted: #65708a;
    --line: #e4e8f2;
    --brand: #2f6fed;
    --brand-soft: #eef3ff;
    --purple: #7c3aed;
    --green: #15803d;
    --orange: #b45309;
    --teal: #0f766e;
    --soft: #fbfcff;
    --code: #f7f9fd;
    --head: #f8fafd;
    --even: #fbfcff;
    --row-line: #f0f3f9;
    --warn-bg: #fff8ef;
    --warn-line: #f3d3a7;
    --warn-ink: #7c3f06;
    --info-bg: #eef6ff;
    --info-line: #c7ddfb;
    --info-ink: #1e4b8f;
}
html[data-theme="dark"] {
    --bg: #0f1420;
    --card: #171e2e;
    --ink: #e8ecf6;
    --muted: #9aa6bf;
    --line: #2a3448;
    --brand: #6b9bff;
    --brand-soft: #1d2942;
    --purple: #a78bfa;
    --green: #4ade80;
    --orange: #fbbf24;
    --teal: #5eead4;
    --soft: #141b29;
    --code: #121826;
    --head: #141b29;
    --even: #141b29;
    --row-line: #232c3e;
    --warn-bg: #2a2113;
    --warn-line: #5a4420;
    --warn-ink: #f3d9a7;
    --info-bg: #14243c;
    --info-line: #2a4a76;
    --info-ink: #c7ddfb;
}
* { box-sizing: border-box; }
body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, Ubuntu, sans-serif;
    line-height: 1.5;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 28px 20px 56px; }
.hero {
    display: flex;
    gap: 20px;
    align-items: center;
    padding: 28px 30px;
    border-radius: 22px;
    background: linear-gradient(135deg, #1f2a4a 0%, #2f6fed 58%, #7c3aed 100%);
    color: #fff;
    box-shadow: 0 18px 42px rgba(31, 42, 74, .26);
}
.hero-icon { font-size: 54px; line-height: 1; }
.eyebrow {
    margin: 0 0 2px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, .7);
}
h1 { margin: 0 0 6px; font-size: 30px; letter-spacing: -.01em; }
.meta { margin: 0; font-size: 14px; color: rgba(255, 255, 255, .84); }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.toolbar button, .toolbar a {
    padding: 8px 14px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: var(--card);
    color: var(--ink);
    font-size: 13px;
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
    box-shadow: 0 3px 10px rgba(28, 35, 51, .05);
}
.toolbar button:hover, .toolbar a:hover {
    border-color: var(--brand);
    color: var(--brand);
}
nav.toc { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0 0; }
nav.toc a {
    padding: 8px 14px;
    border-radius: 999px;
    background: var(--card);
    border: 1px solid var(--line);
    color: var(--ink);
    font-size: 13px;
    font-weight: 600;
    text-decoration: none;
    box-shadow: 0 3px 10px rgba(28, 35, 51, .05);
}
nav.toc a:hover { border-color: var(--brand); color: var(--brand); }
.card {
    margin-top: 18px;
    padding: 22px;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    box-shadow: 0 8px 24px rgba(28, 35, 51, .06);
}
.card h2 {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0 0 14px;
    font-size: 20px;
}
.section-head {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}
.section-head h2 { margin: 0; }
.pill {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--brand-soft);
    color: var(--brand);
    font-size: 11px;
    font-weight: 700;
}
.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.stat {
    padding: 14px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--soft);
}
.stat .label {
    display: block;
    margin-bottom: 4px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--muted);
}
.stat .value { margin: 0; font-size: 14px; }
.alert {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    margin: 8px 0;
    padding: 12px 14px;
    border: 1px solid;
    border-radius: 12px;
    font-size: 14px;
}
.alert p { margin: 0; }
.alert.warn { background: var(--warn-bg); border-color: var(--warn-line); color: var(--warn-ink); }
.alert.info { background: var(--info-bg); border-color: var(--info-line); color: var(--info-ink); }
pre.code {
    margin: 0;
    padding: 14px 16px;
    max-height: 460px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    background: var(--code);
    border: 1px solid var(--line);
    border-radius: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px;
    line-height: 1.55;
}
.muted { color: var(--muted); }
.note { margin: 0 0 14px; font-size: 13px; color: var(--muted); }
.privacy { margin-top: 10px; }
.notice {
    margin-top: 18px;
    padding: 14px 18px;
    border: 1px solid var(--warn-line);
    border-left: 4px solid var(--orange);
    border-radius: 12px;
    background: var(--warn-bg);
    color: var(--warn-ink);
    font-size: 14px;
}
.notice p { margin: 4px 0 0; }
ul.plain { margin: 0; padding-left: 20px; font-size: 14px; }
ul.plain li { margin: 4px 0; }
.search { display: flex; gap: 10px; align-items: center; margin: 6px 0 4px; }
.search input {
    flex: 1;
    padding: 11px 15px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--soft);
    color: var(--ink);
    font-size: 14px;
    outline: none;
}
.search input:focus {
    border-color: var(--brand);
    box-shadow: 0 0 0 3px rgba(47, 111, 237, .14);
}
.prog {
    margin-top: 16px;
    border: 1px solid var(--line);
    border-radius: 14px;
    overflow: hidden;
}
.prog-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: var(--head);
    border-bottom: 1px solid var(--line);
}
.prog-head h3 { margin: 0; font-size: 15px; }
.count {
    display: inline-block;
    margin-left: 6px;
    padding: 2px 9px;
    border-radius: 999px;
    background: var(--brand);
    color: #fff;
    font-size: 11px;
    font-weight: 800;
}
.prog-snap .count { background: var(--orange); }
.prog-flatpak_apps .count { background: var(--teal); }
.shown { font-size: 12px; font-weight: 600; color: var(--muted); }
.table-wrap { max-height: 380px; overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    padding: 9px 16px;
    background: var(--card);
    border-bottom: 1px solid var(--line);
    text-align: left;
    font-size: 11px;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--muted);
}
table.sortable thead th { cursor: pointer; user-select: none; }
table.sortable thead th[data-dir="asc"]::after { content: " ▲"; }
table.sortable thead th[data-dir="desc"]::after { content: " ▼"; }
tbody td { padding: 8px 16px; border-bottom: 1px solid var(--row-line); }
tbody tr:nth-child(even) { background: var(--even); }
tbody tr:hover { background: var(--brand-soft); }
td.name { font-weight: 600; }
td.ver { color: var(--muted); white-space: nowrap; }
td.size { color: var(--muted); white-space: nowrap; }
td.num { white-space: nowrap; }
footer {
    margin-top: 28px;
    text-align: center;
    font-size: 12px;
    color: var(--muted);
}
@media (max-width: 760px) {
    .stats { grid-template-columns: 1fr; }
    .hero { flex-direction: column; align-items: flex-start; }
}
@media print {
    body { background: #fff; }
    .wrap { max-width: none; padding: 0; }
    .hero, nav.toc, .card, .stat, .notice, .count, .alert {
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }
    .hero { box-shadow: none; }
    .toolbar, nav.toc, .search { display: none; }
    .card { box-shadow: none; break-inside: avoid; }
    .table-wrap, pre.code { max-height: none; overflow: visible; }
    thead th { position: static; }
}
"""

_REPORT_JS = """
(function () {
    var root = document.documentElement;
    try {
        var saved = localStorage.getItem('cleanix-theme');
        if (saved === 'dark' || saved === 'light') {
            root.setAttribute('data-theme', saved);
        }
    } catch (e) {}

    var theme = document.getElementById('xray-theme');
    if (theme) {
        theme.addEventListener('click', function () {
            var next = root.getAttribute('data-theme') === 'dark'
                ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            try { localStorage.setItem('cleanix-theme', next); } catch (e) {}
        });
    }

    var printBtn = document.getElementById('xray-print');
    if (printBtn) {
        printBtn.addEventListener('click', function () { window.print(); });
    }

    var topBtn = document.getElementById('xray-top');
    if (topBtn) {
        topBtn.addEventListener('click', function (event) {
            event.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    document.querySelectorAll('table.sortable thead th').forEach(
        function (th, index) {
            th.addEventListener('click', function () {
                var table = th.closest('table');
                var body = table.tBodies[0];
                var rows = Array.prototype.slice.call(body.rows);
                var dir = th.getAttribute('data-dir') === 'asc' ? -1 : 1;
                table.querySelectorAll('thead th').forEach(function (h) {
                    h.removeAttribute('data-dir');
                });
                th.setAttribute('data-dir', dir === 1 ? 'asc' : 'desc');
                rows.sort(function (a, b) {
                    var av = a.cells[index]
                        ? a.cells[index].textContent.trim() : '';
                    var bv = b.cells[index]
                        ? b.cells[index].textContent.trim() : '';
                    return av.localeCompare(
                        bv, undefined, { numeric: true }) * dir;
                });
                rows.forEach(function (row) { body.appendChild(row); });
            });
        });

    var input = document.getElementById('xray-search');
    if (!input) { return; }
    function apply() {
        var term = input.value.trim().toLowerCase();
        document.querySelectorAll('.prog').forEach(function (section) {
            var rows = section.querySelectorAll('tbody tr');
            var shown = 0;
            rows.forEach(function (row) {
                var hit = !term
                    || row.textContent.toLowerCase().indexOf(term) !== -1;
                row.hidden = !hit;
                if (hit && row.querySelector('td:not([colspan])')) {
                    shown++;
                }
            });
            var counter = section.querySelector('.shown');
            if (counter) {
                counter.textContent = shown + ' / ' + rows.length;
            }
        });
    }
    input.addEventListener('input', apply);
    apply();
})();
"""


def build_report_html(snapshot, bios_details='', hw_details='',
                      bios_source='', hw_source='', priv_error='',
                      redact=True):
    """Monta o relatório HTML completo (autocontido) do Raio-X."""
    import html as html_lib
    from datetime import datetime

    snap = snapshot or {}
    bios = snap.get('bios', {}) or {}
    hardware = snap.get('hardware', {}) or {}
    programs = snap.get('programs', {}) or {}
    network = snap.get('network', {}) or {}
    system = snap.get('system', {}) or {}
    disks = snap.get('disks', []) or []
    alerts = snap.get('alerts', []) or []
    fields = bios.get('fields') or {}
    limitations = snap.get('limitations') or []

    def esc(value):
        return html_lib.escape(str(value or ''))

    def code_block(text):
        if not text:
            return ('<p class="muted">'
                    + esc(i18n.t('xray.unavailable')) + '</p>')
        return '<pre class="code">' + esc(text) + '</pre>'

    bios_details = bios_details or bios.get('details') or ''
    hw_details = hw_details or hardware.get('details') or ''
    if redact:
        bios_details = redact_sensitive(bios_details)
        hw_details = redact_sensitive(hw_details)
        network_details = redact_network_macs(network.get('details') or '')
    else:
        network_details = network.get('details') or ''

    product = fields.get('product_name') or fields.get('sys_vendor') or ''
    os_name = os_pretty_name()
    generated = datetime.now().strftime('%d/%m/%Y %H:%M')
    meta_bits = [b for b in (product, os_name) if b]
    meta_bits.append(i18n.t('xray.html.generated', date=generated))
    meta = ' · '.join(meta_bits)

    def program_section(key, title, icon):
        items = programs.get(key) or []
        rows = []
        for item in items:
            name = item[0] if item else ''
            version = item[1] if len(item) > 1 else ''
            size = item[2] if len(item) > 2 else ''
            rows.append(
                '<tr><td class="name">' + esc(name) + '</td>'
                '<td class="ver">' + esc(version) + '</td>'
                '<td class="size">' + esc(size) + '</td></tr>')
        if not rows:
            rows.append(
                '<tr><td colspan="3" class="muted">'
                + esc(i18n.t('xray.empty')) + '</td></tr>')
        return (
            '<div class="prog prog-' + esc(key) + '">'
            '<div class="prog-head"><h3>' + esc(icon) + ' ' + esc(title)
            + ' <span class="count">' + str(len(items)) + '</span></h3>'
            + '<span class="shown">' + str(len(items)) + ' / '
            + str(len(items)) + '</span></div>'
            '<div class="table-wrap"><table class="sortable"><thead><tr><th>'
            + esc(i18n.t('xray.col_name')) + '</th><th>'
            + esc(i18n.t('xray.col_version')) + '</th><th>'
            + esc(i18n.t('xray.col_size')) + '</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div></div>')

    runtimes = programs.get('flatpak_runtimes', 0)
    program_html = (
        program_section('apt', i18n.t('xray.programs.apt'), '📦')
        + program_section('snap', i18n.t('xray.programs.snap'), '🟠')
        + program_section('flatpak_apps', i18n.t('xray.programs.flatpak'), '🫐')
    )

    notice = ''
    if priv_error:
        notice = (
            '<div class="notice"><strong>'
            + esc(i18n.t('xray.html.priv_missing'))
            + '</strong><p>'
            + esc(i18n.t('xray.html.priv_missing_body', detail=priv_error))
            + '</p></div>')

    privacy_note = ''
    if redact:
        privacy_note = (
            '<p class="note privacy">🔒 '
            + esc(i18n.t('xray.html.redacted_notice')) + '</p>')

    alerts_html = ''
    for alert in alerts:
        level = 'warn' if alert.get('level') == 'warn' else 'info'
        icon = '⚠️' if level == 'warn' else 'ℹ️'
        alerts_html += (
            '<div class="alert ' + level + '"><span>' + icon + '</span><p>'
            + esc(alert.get('text')) + '</p></div>')
    if not alerts_html:
        alerts_html = ('<p class="muted">'
                       + esc(i18n.t('xray.html.no_alerts')) + '</p>')

    disk_rows = []
    for disk in disks:
        total = disk.get('size_total') or 0
        used = disk.get('size_used') or 0
        pct = disk.get('pct_used')
        pct_text = f'{pct}%' if pct is not None else ''
        disk_rows.append(
            '<tr><td class="name">' + esc(disk.get('name')) + '</td>'
            '<td>' + esc(disk.get('type')) + '</td>'
            '<td class="num">'
            + esc(systeminfo.format_bytes(total) if total else '') + '</td>'
            '<td class="num">'
            + esc(systeminfo.format_bytes(used) if total else '') + '</td>'
            '<td class="num">' + esc(pct_text) + '</td>'
            '<td>' + esc(disk.get('mount_point')) + '</td></tr>')
    if not disk_rows:
        disk_rows.append(
            '<tr><td colspan="6" class="muted">'
            + esc(i18n.t('disks.none')) + '</td></tr>')

    limitations_html = ''
    if limitations:
        items = ''.join('<li>' + esc(item) + '</li>' for item in limitations)
        limitations_html = (
            '<section class="card" id="observacoes">'
            '<h2>📝 ' + esc(i18n.t('xray.html.notes')) + '</h2>'
            '<ul class="plain">' + items + '</ul></section>')

    total_programs = sum(
        len(programs.get(key) or [])
        for key in ('apt', 'snap', 'flatpak_apps'))

    summary_bios = bios.get('summary') or i18n.t('xray.unavailable')
    summary_hw = hardware.get('summary') or i18n.t('xray.unavailable')
    summary_prog = programs.get('summary') or i18n.t(
        'xray.html.programs_total', n=total_programs)

    doc = (
        '<!doctype html>\n'
        '<html lang="' + esc(i18n.get_language().replace('_', '-'))
        + '" data-theme="light">\n'
        '<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>' + esc(i18n.t('xray.title')) + ' · Cleanix</title>\n'
        '<style>' + _REPORT_CSS + '</style>\n</head>\n'
        '<body id="top">\n'
        '<div class="wrap">\n'
        '<header class="hero"><div class="hero-icon">🖥️</div>'
        '<div><p class="eyebrow">Cleanix</p><h1>'
        + esc(i18n.t('xray.title')) + '</h1><p class="meta">' + esc(meta)
        + '</p></div></header>\n'
        '<div class="toolbar">'
        '<button id="xray-print" type="button">🖨️ '
        + esc(i18n.t('xray.html.print')) + '</button>'
        '<button id="xray-theme" type="button">🌗 '
        + esc(i18n.t('xray.html.theme')) + '</button>'
        '<a id="xray-top" href="#top">⬆️ '
        + esc(i18n.t('xray.html.top')) + '</a>'
        '</div>\n'
        + privacy_note + '\n'
        '<nav class="toc">'
        '<a href="#resumo">🔎 ' + esc(i18n.t('xray.summary')) + '</a>'
        '<a href="#destaques">⭐ ' + esc(i18n.t('xray.html.alerts')) + '</a>'
        '<a href="#bios">🧩 ' + esc(i18n.t('xray.bios')) + '</a>'
        '<a href="#hardware">⚙️ ' + esc(i18n.t('xray.hardware')) + '</a>'
        '<a href="#rede">🌐 ' + esc(i18n.t('xray.section.network')) + '</a>'
        '<a href="#sistema">🩺 ' + esc(i18n.t('xray.section.systeminfo')) + '</a>'
        '<a href="#discos">💽 ' + esc(i18n.t('xray.section.disks')) + '</a>'
        '<a href="#programas">📦 ' + esc(i18n.t('xray.programs')) + '</a>'
        '</nav>\n'
        + notice + '\n'
        '<section class="card" id="resumo">'
        '<h2>🔎 ' + esc(i18n.t('xray.summary')) + '</h2>'
        '<div class="stats">'
        '<div class="stat"><span class="label">🧩 '
        + esc(i18n.t('xray.bios')) + '</span><p class="value">'
        + esc(summary_bios) + '</p></div>'
        '<div class="stat"><span class="label">⚙️ '
        + esc(i18n.t('xray.hardware')) + '</span><p class="value">'
        + esc(summary_hw) + '</p></div>'
        '<div class="stat"><span class="label">📦 '
        + esc(i18n.t('xray.programs')) + '</span><p class="value">'
        + esc(summary_prog) + '</p></div>'
        '</div></section>\n'
        '<section class="card" id="destaques">'
        '<h2>⭐ ' + esc(i18n.t('xray.html.alerts')) + '</h2>'
        + alerts_html + '</section>\n'
        '<section class="card" id="bios">'
        '<div class="section-head"><h2>🧩 ' + esc(i18n.t('xray.bios'))
        + '</h2><span class="pill">'
        + esc(bios_source or i18n.t('xray.source_unprivileged'))
        + '</span></div>' + code_block(bios_details) + '</section>\n'
        '<section class="card" id="hardware">'
        '<div class="section-head"><h2>⚙️ ' + esc(i18n.t('xray.hardware'))
        + '</h2><span class="pill">'
        + esc(hw_source or i18n.t('xray.source_unprivileged'))
        + '</span></div>' + code_block(hw_details) + '</section>\n'
        '<section class="card" id="rede">'
        '<h2>🌐 ' + esc(i18n.t('xray.section.network')) + '</h2>'
        '<p class="note">' + esc(network.get('summary') or '') + '</p>'
        + code_block(network_details) + '</section>\n'
        '<section class="card" id="sistema">'
        '<h2>🩺 ' + esc(i18n.t('xray.section.systeminfo')) + '</h2>'
        '<p class="note">' + esc(system.get('summary') or '') + '</p>'
        + code_block(system.get('details') or '') + '</section>\n'
        '<section class="card" id="discos">'
        '<h2>💽 ' + esc(i18n.t('xray.section.disks')) + '</h2>'
        '<div class="table-wrap"><table class="sortable"><thead><tr><th>'
        + esc(i18n.t('xray.col_disk')) + '</th><th>'
        + esc(i18n.t('xray.col_type')) + '</th><th>'
        + esc(i18n.t('xray.col_total')) + '</th><th>'
        + esc(i18n.t('xray.col_used')) + '</th><th>'
        + esc(i18n.t('xray.col_pct')) + '</th><th>'
        + esc(i18n.t('xray.col_mount')) + '</th></tr></thead><tbody>'
        + ''.join(disk_rows) + '</tbody></table></div></section>\n'
        '<section class="card" id="programas">'
        '<h2>📦 ' + esc(i18n.t('xray.programs')) + '</h2>'
        '<p class="note">'
        + esc(i18n.t('xray.programs.runtimes', n=runtimes)) + '</p>'
        '<div class="search"><input id="xray-search" type="search" '
        'placeholder="' + esc(i18n.t('xray.html.search')) + '"></div>'
        + program_html + '</section>\n'
        + limitations_html
        + '\n<footer>'
        + esc(i18n.t('xray.html.footer')) + ' · Cleanix v'
        + esc(cleanix_version) + ' · '
        + esc(i18n.t('xray.html.generated', date=generated))
        + '</footer>\n'
        '</div>\n<script>' + _REPORT_JS + '</script>\n</body>\n</html>\n')
    return doc


def build_support_summary(snapshot, bios_details='', hw_details='',
                          bios_source='', hw_source='', priv_error='',
                          redact=True):
    """Monta um resumo curto em texto para suporte."""
    snap = snapshot or {}
    bios = snap.get('bios', {}) or {}
    hardware = snap.get('hardware', {}) or {}
    programs = snap.get('programs', {}) or {}
    network = snap.get('network', {}) or {}
    system = snap.get('system', {}) or {}
    disks = snap.get('disks', []) or []
    alerts = snap.get('alerts', []) or []
    limitations = snap.get('limitations', []) or []
    fields = bios.get('fields') or {}

    bios_details = bios_details or bios.get('details') or ''
    hw_details = hw_details or hardware.get('details') or ''
    network_details = network.get('details') or ''
    if redact:
        bios_details = redact_sensitive(bios_details)
        hw_details = redact_sensitive(hw_details)
        network_details = redact_network_macs(network_details)

    generated = datetime.now().strftime('%d/%m/%Y %H:%M')
    product = fields.get('product_name') or fields.get('sys_vendor') or ''
    os_name = os_pretty_name()
    lines = []
    lines.append('Cleanix — ' + i18n.t('xray.title'))
    lines.append(i18n.t('xray.html.generated', date=generated))
    lines.append('Cleanix v' + str(cleanix_version))
    if redact:
        lines.append('🔒 ' + i18n.t('xray.html.redacted_notice'))
    if os_name:
        lines.append(i18n.t('xray.section.os') + ': ' + os_name)
    if product:
        lines.append(i18n.t('xray.field.product_name') + ': ' + product)
    if priv_error:
        lines.append(i18n.t('xray.field.limitations') + ': ' + str(priv_error))

    lines.append('')
    lines.append('[' + i18n.t('xray.bios') + ']')
    lines.append(bios.get('summary') or i18n.t('xray.unavailable'))

    lines.append('')
    lines.append('[' + i18n.t('xray.hardware') + ']')
    lines.append(hardware.get('summary') or i18n.t('xray.unavailable'))

    if bios_details.strip():
        lines.append('')
        lines.append('[' + i18n.t('xray.bios') + ' - detalhes]')
        lines.append(bios_details.strip())
    if hw_details.strip():
        lines.append('')
        lines.append('[' + i18n.t('xray.hardware') + ' - detalhes]')
        lines.append(hw_details.strip())

    lines.append('')
    lines.append('[' + i18n.t('xray.section.disks') + ']')
    if disks:
        for disk in disks:
            name = disk.get('name') or '?'
            dtype = disk.get('type') or ''
            total = disk.get('size_total') or 0
            pct = disk.get('pct_used')
            mount = disk.get('mount_point') or ''
            parts = [name]
            if dtype:
                parts.append('(' + str(dtype) + ')')
            if total:
                parts.append(systeminfo.format_bytes(total))
            if pct is not None:
                parts.append(str(pct) + '%')
            if mount:
                parts.append(mount)
            lines.append(' - ' + ' '.join(str(p) for p in parts))
    else:
        lines.append(i18n.t('disks.none'))

    lines.append('')
    lines.append('[' + i18n.t('xray.section.network') + ']')
    net_summary = network.get('summary') or ''
    if net_summary:
        lines.append(net_summary)
    for iface in network.get('interfaces') or []:
        line = ' - ' + str(iface.get('name') or '')
        state = iface.get('state') or ''
        if state:
            line += ' ' + state
        addrs = iface.get('addresses') or []
        if addrs:
            line += ' | ' + ', '.join(str(a) for a in addrs)
        if not redact and iface.get('mac'):
            line += ' | MAC: ' + str(iface.get('mac'))
        lines.append(line)
    if not net_summary and not (network.get('interfaces') or []):
        lines.append(i18n.t('xray.network.none'))
    if network_details.strip():
        lines.append(network_details.strip())

    lines.append('')
    lines.append('[' + i18n.t('xray.section.systeminfo') + ']')
    lines.append(system.get('summary') or i18n.t('xray.unavailable'))

    lines.append('')
    lines.append('[' + i18n.t('xray.programs') + ']')
    apt_n = len(programs.get('apt') or [])
    snap_n = len(programs.get('snap') or [])
    flat_n = len(programs.get('flatpak_apps') or [])
    runtimes = programs.get('flatpak_runtimes') or 0
    lines.append(f"APT: {apt_n} | Snap: {snap_n} | Flatpak: {flat_n} apps (+{runtimes} runtimes)")

    lines.append('')
    lines.append('[' + i18n.t('xray.html.alerts') + ']')
    if alerts:
        for alert in alerts:
            level = str(alert.get('level') or 'info').upper()
            lines.append(f" - [{level}] {alert.get('text') or ''}")
    else:
        lines.append(i18n.t('xray.html.no_alerts'))

    if limitations:
        lines.append('')
        lines.append('[' + i18n.t('xray.field.limitations') + ']')
        for item in limitations:
            lines.append(' - ' + str(item))

    return '\n'.join(lines)


def _program_items(items):
    result = []
    for item in items or []:
        if not item:
            continue
        result.append({
            'name': item[0] if len(item) > 0 else '',
            'version': item[1] if len(item) > 1 else '',
            'size': item[2] if len(item) > 2 else '',
        })
    return result


def build_report_json(snapshot, bios_details='', hw_details='',
                      bios_source='', hw_source='', priv_error='',
                      redact=True):
    """Monta o relatório JSON do Raio-X."""
    snap = snapshot or {}
    bios = snap.get('bios', {}) or {}
    hardware = snap.get('hardware', {}) or {}
    programs = snap.get('programs', {}) or {}
    network = snap.get('network', {}) or {}
    system = snap.get('system', {}) or {}
    disks = snap.get('disks', []) or []
    alerts = snap.get('alerts', []) or []
    limitations = snap.get('limitations', []) or []
    fields = dict(bios.get('fields') or {})

    bios_details = bios_details or bios.get('details') or ''
    hw_details = hw_details or hardware.get('details') or ''
    network_details = network.get('details') or ''
    if redact:
        bios_details = redact_sensitive(bios_details)
        hw_details = redact_sensitive(hw_details)
        network_details = redact_network_macs(network_details)

    interfaces = []
    for iface in network.get('interfaces') or []:
        item = dict(iface)
        if redact and 'mac' in item:
            item['mac'] = i18n.t('xray.redacted')
        interfaces.append(item)

    data = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cleanix_version': str(cleanix_version),
            'os': os_pretty_name(),
            'product': fields.get('product_name') or fields.get('sys_vendor') or '',
            'redacted': bool(redact),
            'priv_error': priv_error or '',
        },
        'bios': {
            'summary': bios.get('summary') or '',
            'details': bios_details,
            'source': bios_source or '',
            'fields': fields,
        },
        'hardware': {
            'summary': hardware.get('summary') or '',
            'details': hw_details,
            'source': hw_source or '',
        },
        'network': {
            'summary': network.get('summary') or '',
            'details': network_details,
            'interfaces': interfaces,
        },
        'system': dict(system),
        'disks': list(disks),
        'alerts': list(alerts),
        'programs': {
            'summary': programs.get('summary') or '',
            'apt': _program_items(programs.get('apt')),
            'snap': _program_items(programs.get('snap')),
            'flatpak_apps': _program_items(programs.get('flatpak_apps')),
            'flatpak_runtimes': programs.get('flatpak_runtimes') or 0,
        },
        'limitations': list(limitations),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_report_csv(snapshot, bios_details='', hw_details='',
                     bios_source='', hw_source='', priv_error='',
                     redact=True):
    """Monta o relatório CSV do Raio-X."""
    snap = snapshot or {}
    programs = snap.get('programs', {}) or {}
    disks = snap.get('disks', []) or []
    alerts = snap.get('alerts', []) or []

    output = io.StringIO()
    writer = csv.writer(output)
    header = ['section', 'origin', 'name', 'version', 'size',
              'type', 'total', 'used', 'pct', 'mount', 'level', 'text']
    writer.writerow(header)

    for origin, key in (('apt', 'apt'), ('snap', 'snap'), ('flatpak', 'flatpak_apps')):
        for item in programs.get(key) or []:
            if not item:
                continue
            name = item[0] if len(item) > 0 else ''
            version = item[1] if len(item) > 1 else ''
            size = item[2] if len(item) > 2 else ''
            writer.writerow(['program', origin, name, version, size,
                             '', '', '', '', '', '', ''])

    for disk in disks:
        total = disk.get('size_total') or 0
        used = disk.get('size_used') or 0
        pct = disk.get('pct_used')
        writer.writerow([
            'disk', '', disk.get('name') or '', '', '',
            disk.get('type') or '',
            systeminfo.format_bytes(total) if total else '',
            systeminfo.format_bytes(used) if total else '',
            str(pct) + '%' if pct is not None else '',
            disk.get('mount_point') or '', '', '',
        ])

    for alert in alerts:
        writer.writerow(['alert', '', '', '', '', '', '', '', '', '',
                         alert.get('level') or '', alert.get('text') or ''])

    return output.getvalue()
