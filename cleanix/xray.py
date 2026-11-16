#!/usr/bin/env python3
"""Coleta de inventário da máquina (Raio-X): BIOS, hardware e programas."""

from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path

from . import i18n, systeminfo
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
    sections = []
    sys_lines = []
    for k in ('sys_vendor', 'product_name', 'product_version', 'chassis_vendor'):
        if k in fields:
            sys_lines.append(f"• {labels.get(k, k)}: {fields[k]}")
    if sys_lines:
        sections.append("Sistema\n" + "\n".join(sys_lines))

    board_lines = []
    for k in ('board_vendor', 'board_name'):
        if k in fields:
            board_lines.append(f"• {labels.get(k, k)}: {fields[k]}")
    if board_lines:
        sections.append("Placa-mãe\n" + "\n".join(board_lines))

    bios_lines = []
    for k in ('bios_vendor', 'bios_version', 'bios_date'):
        if k in fields:
            bios_lines.append(f"• {labels.get(k, k)}: {fields[k]}")
    if bios_lines:
        sections.append("BIOS/Firmware\n" + "\n".join(bios_lines))

    try:
        u = os.uname()
        sections.append("Sistema operacional\n"
                        f"• Kernel: {u.release}\n"
                        f"• Arquitetura: {u.machine}")
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
        summary_parts.append(f"CPU: {cpu_model or 'N/D'} ({cores} núcleos lógicos)")
    detail_lines.append('▸ CPU')
    if cpu_model:
        detail_lines.append(f"  • Modelo: {cpu_model}")
    detail_lines.append(f"  • Núcleos lógicos: {cores}")
    if shutil.which('lscpu'):
        lscpu = _cmd('lscpu')
        if lscpu:
            # keep compact but readable highlights
            wanted = ('Architecture:', 'CPU(s):', 'Model name:', 'Thread(s) per core:',
                      'Core(s) per socket:', 'Socket(s):', 'CPU max MHz:', 'CPU min MHz:',
                      'Vendor ID:', 'Virtualization:')
            highlights = [ln for ln in lscpu.splitlines() if ln.startswith(wanted)]
            if highlights:
                detail_lines.append('')
                detail_lines.extend('  ' + ln for ln in highlights)

    # Memory
    mem = systeminfo.get_mem_info()
    if mem.total:
        summary_parts.append(f"RAM: {systeminfo.format_bytes(mem.total)}")
    detail_lines.append('\n▸ Memória')
    if mem.total:
        detail_lines.append(f"  • Total: {systeminfo.format_bytes(mem.total)}")
        detail_lines.append(f"  • Disponível: {systeminfo.format_bytes(mem.available)}")
        detail_lines.append(f"  • Em uso: {systeminfo.format_bytes(mem.used)}")
    else:
        detail_lines.append('  • Indisponível')

    # Disks
    try:
        disks = systeminfo._scan_disks()
        phys = [d for d in disks if d.get('type') == 'disk' and (d.get('size_total') or 0) > 0]
        if phys:
            names = ', '.join(
                f"{d.get('name')} ({systeminfo.format_bytes(d.get('size_total', 0))})" for d in phys[:4])
            summary_parts.append(f"Discos: {names}")
        detail_lines.append('\n▸ Discos e partições')
        if disks:
            for d in disks[:20]:
                t = systeminfo.format_bytes(d.get('size_total', 0))
                mp = d.get('mount_point') or ''
                dtype = d.get('type') or ''
                prefix = '  •' if dtype == 'disk' else '    -'
                extra = f"  [{mp}]" if mp else ''
                detail_lines.append(f"{prefix} {d.get('name')} ({dtype}, {t}){extra}")
        else:
            detail_lines.append('  • Indisponível')
    except Exception:
        detail_lines.append('\n▸ Discos e partições')
        detail_lines.append('  • Indisponível')

    # PCI/GPU/USB
    if shutil.which('lspci'):
        lspci = _cmd('lspci -nn')
        if lspci:
            gpus = [ln for ln in lspci.splitlines()
                    if re.search(r'VGA|3D|Display', ln, re.I)]
            if gpus:
                summary_parts.append(f"GPU: {gpus[0].split(': ', 1)[-1][:60]}")
            detail_lines.append('\n▸ GPU (PCI)')
            for g in gpus[:6]:
                detail_lines.append('  • ' + g.split(': ', 1)[-1])
            detail_lines.append('\n▸ Dispositivos PCI')
            # show concise list (limit to avoid wall of text)
            pci_lines = lspci.splitlines()
            for ln in pci_lines[:40]:
                detail_lines.append('  • ' + ln)
            if len(pci_lines) > 40:
                detail_lines.append(f'  … (+{len(pci_lines)-40} itens)')
    else:
        limitations.append('lspci indisponível')
        detail_lines.append('\n▸ PCI')
        detail_lines.append('  • Indisponível (lspci)')

    if shutil.which('lsusb'):
        lsusb = _cmd('lsusb')
        if lsusb:
            detail_lines.append('\n▸ USB')
            for ln in lsusb.splitlines()[:30]:
                detail_lines.append('  • ' + ln)
            usb_lines = lsusb.splitlines()
            if len(usb_lines) > 30:
                detail_lines.append(f'  … (+{len(usb_lines)-30} itens)')
    else:
        limitations.append('lsusb indisponível')

    summary = ' | '.join(summary_parts) if summary_parts else 'Hardware: informações limitadas'
    details = '\n'.join(detail_lines).strip()
    if limitations:
        details += '\n\n⚠ Limitações: ' + ', '.join(limitations)
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
            'error': 'dmidecode e lshw não encontrados',
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
            res.error or 'Falha ao coletar os detalhes completos'),
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
nav.toc { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0 0; }
nav.toc a {
    padding: 8px 14px;
    border-radius: 999px;
    background: #fff;
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
    background: #fbfcff;
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
pre.code {
    margin: 0;
    padding: 14px 16px;
    max-height: 460px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    background: #f7f9fd;
    border: 1px solid var(--line);
    border-radius: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px;
    line-height: 1.55;
}
.muted { color: var(--muted); }
.note { margin: 0 0 14px; font-size: 13px; color: var(--muted); }
.notice {
    margin-top: 18px;
    padding: 14px 18px;
    border: 1px solid #f3d3a7;
    border-left: 4px solid var(--orange);
    border-radius: 12px;
    background: #fff8ef;
    color: #7c3f06;
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
    background: #fbfcff;
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
    background: #f8fafd;
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
    background: #fff;
    border-bottom: 1px solid var(--line);
    text-align: left;
    font-size: 11px;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--muted);
}
tbody td { padding: 8px 16px; border-bottom: 1px solid #f0f3f9; }
tbody tr:nth-child(even) { background: #fbfcff; }
tbody tr:hover { background: var(--brand-soft); }
td.name { font-weight: 600; }
td.ver { color: var(--muted); white-space: nowrap; }
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
    .hero, nav.toc, .card, .stat, .notice, .count {
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }
    .hero { box-shadow: none; }
    nav.toc, .search { display: none; }
    .card { box-shadow: none; break-inside: avoid; }
    .table-wrap, pre.code { max-height: none; overflow: visible; }
    thead th { position: static; }
}
"""

_REPORT_JS = """
(function () {
    var input = document.getElementById('xray-search');
    if (!input) { return; }
    function apply() {
        var term = input.value.trim().toLowerCase();
        document.querySelectorAll('.prog').forEach(function (section) {
            var rows = section.querySelectorAll('tbody tr');
            var shown = 0;
            rows.forEach(function (row) {
                var hit = !term || row.textContent.toLowerCase().indexOf(term) !== -1;
                row.hidden = !hit;
                if (hit && row.querySelector('td')) { shown++; }
            });
            var counter = section.querySelector('.shown');
            if (counter) { counter.textContent = shown + ' / ' + rows.length; }
        });
    }
    input.addEventListener('input', apply);
    apply();
})();
"""


def build_report_html(snapshot, bios_details='', hw_details='',
                      bios_source='', hw_source='', priv_error=''):
    """Monta o relatório HTML completo (autocontido) do Raio-X."""
    import html as html_lib
    from datetime import datetime

    snap = snapshot or {}
    bios = snap.get('bios', {}) or {}
    hardware = snap.get('hardware', {}) or {}
    programs = snap.get('programs', {}) or {}
    fields = bios.get('fields') or {}
    limitations = snap.get('limitations') or []

    def esc(value):
        return html_lib.escape(str(value or ''))

    def code_block(text):
        if not text:
            return ('<p class="muted">'
                    + esc(i18n.t('xray.unavailable')) + '</p>')
        return '<pre class="code">' + esc(text) + '</pre>'

    product = fields.get('product_name') or fields.get('sys_vendor') or ''
    os_name = os_pretty_name()
    generated = datetime.now().strftime('%d/%m/%Y %H:%M')
    meta_bits = [b for b in (product, os_name) if b]
    meta_bits.append(i18n.t('xray.html.generated', date=generated))
    meta = ' · '.join(meta_bits)

    def program_section(key, title, icon):
        items = programs.get(key) or []
        rows = []
        for name, version in items:
            rows.append(
                '<tr><td class="name">' + esc(name) + '</td>'
                '<td class="ver">' + esc(version) + '</td></tr>')
        if not rows:
            rows.append(
                '<tr><td colspan="2" class="muted">'
                + esc(i18n.t('xray.empty')) + '</td></tr>')
        return (
            '<div class="prog prog-' + esc(key) + '">'
            '<div class="prog-head"><h3>' + esc(icon) + ' ' + esc(title)
            + ' <span class="count">' + str(len(items)) + '</span></h3>'
            + '<span class="shown">' + str(len(items)) + ' / '
            + str(len(items)) + '</span></div>'
            '<div class="table-wrap"><table><thead><tr><th>'
            + esc(i18n.t('xray.col_name')) + '</th><th>'
            + esc(i18n.t('xray.col_version')) + '</th></tr></thead><tbody>'
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
        '<html lang="' + esc(i18n.get_language().replace('_', '-')) + '">\n'
        '<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>' + esc(i18n.t('xray.title')) + ' · Cleanix</title>\n'
        '<style>' + _REPORT_CSS + '</style>\n</head>\n<body>\n'
        '<div class="wrap">\n'
        '<header class="hero"><div class="hero-icon">🖥️</div>'
        '<div><p class="eyebrow">Cleanix</p><h1>'
        + esc(i18n.t('xray.title')) + '</h1><p class="meta">' + esc(meta)
        + '</p></div></header>\n'
        '<nav class="toc">'
        '<a href="#resumo">🔎 ' + esc(i18n.t('xray.summary')) + '</a>'
        '<a href="#bios">🧩 ' + esc(i18n.t('xray.bios')) + '</a>'
        '<a href="#hardware">⚙️ ' + esc(i18n.t('xray.hardware')) + '</a>'
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
        '<section class="card" id="programas">'
        '<h2>📦 ' + esc(i18n.t('xray.programs')) + '</h2>'
        '<p class="note">'
        + esc(i18n.t('xray.programs.runtimes', n=runtimes)) + '</p>'
        '<div class="search"><input id="xray-search" type="search" '
        'placeholder="' + esc(i18n.t('xray.html.search')) + '"></div>'
        + program_html + '</section>\n'
        + limitations_html
        + '\n<footer>'
        + esc(i18n.t('xray.html.footer')) + ' · Cleanix</footer>\n'
        '</div>\n<script>' + _REPORT_JS + '</script>\n</body>\n</html>\n')
    return doc
