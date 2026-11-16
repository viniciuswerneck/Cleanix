#!/usr/bin/env python3
"""Leitura de dados reais do sistema: disco, memória e CPU."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
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




def _scan_disks() -> list[dict]:
    """Lista discos e partições com tamanho e uso.

    Inclui discos físicos (mesmo sem montagem) e partições montadas.
    Retorna lista de dicts com name, size_total, size_used, size_free,
    pct_used, mounted, mount_point.
    """
    import json
    import subprocess

    disks: list[dict] = []
    seen: set[str] = set()

    def _add(entry: dict) -> None:
        key = (entry.get('name'), entry.get('mount_point') or '')
        if key in seen:
            return
        seen.add(key)
        disks.append(entry)

    def _df_usage(mount: str) -> tuple[int, int, int, int] | None:
        try:
            out = subprocess.check_output(
                ['df', '-B1', mount], text=True, stderr=subprocess.DEVNULL
            ).strip().splitlines()
            if len(out) < 2:
                return None
            parts = out[1].split()
            if len(parts) < 3:
                return None
            total = int(parts[1])
            used = int(parts[2])
            free = total - used
            pct = round(100.0 * used / total) if total > 0 else 0
            return total, used, free, pct
        except Exception:
            return None

    try:
        lsblk_out = subprocess.check_output(
            ['lsblk', '-Jb', '-o', 'NAME,TYPE,SIZE,MOUNTPOINT,MODEL'],
            text=True, stderr=subprocess.DEVNULL,
        )
        data = json.loads(lsblk_out)
        for device in data.get('blockdevices', []):
            if device.get('type') != 'disk':
                continue
            name = device.get('name') or 'disco'
            model = (device.get('model') or '').strip() or name
            total = int(device.get('size') or 0)
            mount = device.get('mountpoint')
            # aggregate usage from mounted children when disk itself not mounted
            children = device.get('children') or []
            mounted_children = [c for c in children if c.get('mountpoint')]
            usage = _df_usage(mount) if mount else None
            agg_used = 0
            agg_total = 0
            for c in mounted_children:
                cu = _df_usage(c.get('mountpoint'))
                if cu:
                    agg_total += cu[0]
                    agg_used += cu[1]
            if usage:
                t, u, f, p = usage
                _add({
                    'name': name, 'model': model, 'type': 'disk',
                    'size_total': t, 'size_used': u, 'size_free': f,
                    'pct_used': p, 'mounted': True, 'mount_point': mount,
                })
            else:
                if agg_total > 0:
                    free = max(0, agg_total - agg_used)
                    pct = round(100.0 * agg_used / agg_total)
                    _add({
                        'name': name, 'model': model, 'type': 'disk',
                        'size_total': total, 'size_used': agg_used,
                        'size_free': max(0, total - agg_used),
                        'pct_used': pct, 'mounted': False, 'mount_point': '',
                        'has_mounted_parts': True,
                    })
                else:
                    _add({
                        'name': name, 'model': model, 'type': 'disk',
                        'size_total': total, 'size_used': 0, 'size_free': total,
                        'pct_used': 0, 'mounted': False, 'mount_point': '',
                    })

            for child in children:
                if child.get('type') not in ('part', 'lvm', 'crypt'):
                    continue
                cname = child.get('name') or 'partição'
                cmount = child.get('mountpoint')
                ctotal = int(child.get('size') or 0)
                cusage = _df_usage(cmount) if cmount else None
                if cusage:
                    t, u, f, p = cusage
                    _add({
                        'name': cname, 'model': model, 'type': child.get('type'),
                        'size_total': t, 'size_used': u, 'size_free': f,
                        'pct_used': p, 'mounted': True, 'mount_point': cmount,
                        'parent': name,
                    })
                elif ctotal > 0:
                    _add({
                        'name': cname, 'model': model, 'type': child.get('type'),
                        'size_total': ctotal, 'size_used': 0, 'size_free': ctotal,
                        'pct_used': 0, 'mounted': False, 'mount_point': cmount or '',
                        'parent': name,
                    })
    except Exception:
        pass

    return disks

def health_state(percent_free: float) -> str:
    if percent_free >= 20:
        return "ok"
    if percent_free >= 10:
        return "warn"
    return "bad"


def smartctl_available() -> bool:
    return shutil.which('smartctl') is not None


def physical_disks_for_smart(disks: list[dict] | None = None) -> list[dict]:
    if disks is None:
        disks = _scan_disks()
    out = []
    for d in disks:
        name = d.get('name') or ''
        if d.get('type') != 'disk':
            continue
        if (d.get('size_total') or 0) <= 0:
            continue
        if name.startswith(('loop', 'zram', 'ram')):
            continue
        out.append(d)
    return out


_CRITICAL_ATTRS = {
    'Reallocated_Sector_Ct',
    'Current_Pending_Sector',
    'Offline_Uncorrectable',
    'Reported_Uncorrect',
    'Reallocated_Event_Count',
}


def parse_smartctl(text: str) -> dict:
    overall = 'unknown'
    overall_text = ''
    m = re.search(
        r'(SMART overall-health self-assessment test result:\s*(PASSED|FAILED)!?)',
        text, re.IGNORECASE,
    )
    if m:
        overall_text = m.group(1).strip()
        overall = 'passed' if m.group(2).upper() == 'PASSED' else 'failed'

    attributes = []
    for line in text.splitlines():
        am = re.match(r'^\s*(\d+)\s+(\S+)\s+(.*)$', line)
        if not am:
            continue
        try:
            int(am.group(1))
        except ValueError:
            continue
        name = am.group(2)
        rest = am.group(3).strip()
        parts = rest.split()
        raw = parts[-1] if parts else ''
        # common format has RAW_VALUE as last column (may be multi-token rarely)
        if len(parts) >= 6:
            raw = ' '.join(parts[5:])
        value = parts[0] if parts else ''
        attributes.append({
            'name': name,
            'value': value,
            'raw': raw,
            'critical': name in _CRITICAL_ATTRS,
        })
    if len(attributes) > 40:
        attributes = attributes[:40]

    return {
        'overall': overall,
        'overall_text': overall_text,
        'attributes': attributes,
        'notes': [],
    }


def _read_sys_text(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return ''


def read_thermal_temps(base_path='/sys/class/thermal'):
    base = Path(base_path)
    temps = []
    try:
        zones = sorted(base.glob('thermal_zone*'))
    except OSError:
        return temps
    for zone in zones:
        raw = _read_sys_text(zone / 'temp')
        try:
            temp_c = float(raw) / 1000.0
        except (TypeError, ValueError):
            continue
        if temp_c <= 0 or temp_c > 150:
            continue
        zone_type = _read_sys_text(zone / 'type') or zone.name
        temps.append({'type': zone_type, 'temp_c': round(temp_c, 1)})
    return temps


def read_hwmon_temps(base_path='/sys/class/hwmon'):
    base = Path(base_path)
    temps = []
    try:
        hwmons = sorted(base.glob('hwmon*'))
    except OSError:
        return temps
    for hw in hwmons:
        name = _read_sys_text(hw / 'name') or hw.name
        try:
            inputs = sorted(hw.glob('temp*_input'))
        except OSError:
            continue
        for inp in inputs:
            raw = _read_sys_text(inp)
            try:
                temp_c = float(raw) / 1000.0
            except (TypeError, ValueError):
                continue
            if temp_c <= 0 or temp_c > 150:
                continue
            label_path = Path(str(inp).replace('_input', '_label'))
            label = _read_sys_text(label_path) or inp.name.replace('_input', '')
            temps.append({'name': name, 'label': label, 'temp_c': round(temp_c, 1)})
    return temps


def collect_sensors(thermal_path='/sys/class/thermal', hwmon_path='/sys/class/hwmon'):
    readings = []
    # prefer hwmon labels, but include thermal zones not obviously duplicated
    for item in read_hwmon_temps(hwmon_path):
        readings.append({
            'source': 'hwmon',
            'name': item.get('name', ''),
            'label': item.get('label', ''),
            'temp_c': item.get('temp_c'),
        })
    for item in read_thermal_temps(thermal_path):
        readings.append({
            'source': 'thermal',
            'name': item.get('type', ''),
            'label': item.get('type', ''),
            'temp_c': item.get('temp_c'),
        })
    # summary: hottest reading
    summary = ''
    if readings:
        hottest = max(readings, key=lambda r: r.get('temp_c') or 0)
        label = hottest.get('label') or hottest.get('name') or ''
        temp = hottest.get('temp_c')
        if temp is not None:
            summary = f"{label}: {temp:.0f} °C" if label else f"{temp:.0f} °C"
    return {'summary': summary, 'readings': readings}


def _read_power_value(base, names):
    for name in names:
        val = _read_sys_text(base / name)
        if val:
            return val
    return ''


def read_power_supply(base_path='/sys/class/power_supply'):
    base = Path(base_path)
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return {'present': False, 'summary': ''}
    ac_online = None
    battery = None
    for entry in entries:
        kind = _read_sys_text(entry / 'type').lower()
        if kind == 'mains':
            val = _read_sys_text(entry / 'online')
            if val in ('1', '0'):
                ac_online = val == '1'
        elif kind == 'battery' and battery is None:
            battery = entry
    if battery is None:
        return {'present': False, 'summary': '', 'ac_online': ac_online}
    status = _read_sys_text(battery / 'status')
    cap_raw = _read_sys_text(battery / 'capacity')
    try:
        capacity = int(float(cap_raw))
    except (TypeError, ValueError):
        capacity = None
    cyc_raw = _read_sys_text(battery / 'cycle_count')
    try:
        cycle_count = int(float(cyc_raw))
    except (TypeError, ValueError):
        cycle_count = None
    full_raw = _read_power_value(battery, ('energy_full', 'charge_full'))
    design_raw = _read_power_value(battery, ('energy_full_design', 'charge_full_design'))
    health_pct = None
    try:
        full = float(full_raw)
        design = float(design_raw)
        if design > 0 and full > 0:
            health_pct = round((full / design) * 100.0, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        health_pct = None
    parts = []
    if capacity is not None:
        parts.append(f"{capacity}%")
    if status:
        parts.append(status)
    if health_pct is not None:
        parts.append(f"health {health_pct:.0f}%")
    if cycle_count is not None:
        parts.append(f"{cycle_count} cycles")
    summary = ', '.join(parts)
    return {
        'present': True,
        'status': status,
        'capacity': capacity,
        'health_pct': health_pct,
        'cycle_count': cycle_count,
        'ac_online': ac_online,
        'summary': summary,
    }
