"""Leitura e ativação dos aplicativos que iniciam junto com o sistema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SYSTEM_DIRS = (
    Path('/etc/xdg/autostart'),
    Path('/usr/share/gnome/autostart'),
)

DESKTOP_ENTRY = 'Desktop Entry'


@dataclass(frozen=True)
class StartupEntry:
    """Um aplicativo de inicialização encontrado no sistema."""

    name: str
    command: str
    path: Path
    hidden: bool
    user_file: bool


def parse_desktop_file(path) -> dict[str, str]:
    """Devolve as chaves da seção ``[Desktop Entry]`` de um arquivo .desktop."""
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return values

    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            continue
        if section != DESKTOP_ENTRY or '=' not in line:
            continue
        key, _, value = line.partition('=')
        values[key.strip()] = value.strip()
    return values


def display_name(values: dict[str, str], path) -> str:
    """Nome visível, preferindo o português quando existir."""
    for key in ('Name[pt_BR]', 'Name[pt]', 'Name'):
        name = values.get(key)
        if name:
            return name
    return Path(path).stem


def is_hidden(values: dict[str, str]) -> bool:
    """True quando a entrada está desativada pelo usuário."""
    if values.get('Hidden', '').strip().lower() == 'true':
        return True
    return values.get('X-GNOME-Autostart-enabled',
                      '').strip().lower() == 'false'


def list_entries(home, system_dirs=SYSTEM_DIRS) -> list[StartupEntry]:
    """Lista as entradas de inicialização, com o usuário sobrepondo o sistema."""
    home = Path(home)
    user_dir = home / '.config' / 'autostart'

    found: dict[str, StartupEntry] = {}
    for directory in tuple(system_dirs) + (user_dir,):
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob('*.desktop')):
            values = parse_desktop_file(path)
            if not values:
                continue
            found[path.name] = StartupEntry(
                name=display_name(values, path),
                command=values.get('Exec', ''),
                path=path,
                hidden=is_hidden(values),
                user_file=directory == user_dir,
            )
    return sorted(found.values(), key=lambda entry: entry.name.lower())


def _write_entry(path: Path, values: dict[str, str]) -> None:
    lines = ['[Desktop Entry]']
    lines += [f'{key}={value}' for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def set_enabled(entry: StartupEntry, enabled: bool, home) -> None:
    """Ativa ou desativa ``entry`` sem precisar de administrador.

    Entradas do sistema são desativadas por um arquivo de mesmo nome em
    ``~/.config/autostart``; reativar remove esse arquivo.
    """
    home = Path(home)
    target = home / '.config' / 'autostart' / entry.path.name

    if enabled and not entry.user_file:
        if target.exists():
            target.unlink()
        return

    values = parse_desktop_file(entry.path)
    values['Hidden'] = 'false' if enabled else 'true'
    values['X-GNOME-Autostart-enabled'] = 'true' if enabled else 'false'
    _write_entry(target, values)
