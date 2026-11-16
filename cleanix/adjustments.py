#!/usr/bin/env python3
"""Ajustes do GNOME aplicados com gsettings, sem privilégios de root."""

from __future__ import annotations

from .execution import Result, execute_command

INTERFACE_SCHEMA = 'org.gnome.desktop.interface'
PRIVACY_SCHEMA = 'org.gnome.desktop.privacy'


def parse_gsettings_bool(text: str) -> bool | None:
    """Converte a saída de ``gsettings get`` em booleano."""
    value = (text or '').strip().lower()
    if value == 'true':
        return True
    if value == 'false':
        return False
    return None


def _get_bool(key: str) -> bool | None:
    result = execute_command(f'gsettings get {key}')
    if not result.ok:
        return None
    return parse_gsettings_bool(result.output)


def _set_bool(command: str) -> Result:
    return execute_command(command)


def get_animations() -> bool | None:
    return _get_bool(f'{INTERFACE_SCHEMA} enable-animations')


def set_animations(enabled: bool) -> Result:
    value = 'true' if enabled else 'false'
    return _set_bool(
        f'gsettings set {INTERFACE_SCHEMA} enable-animations {value}')


def get_privacy_cleanup() -> bool | None:
    return _get_bool(f'{PRIVACY_SCHEMA} remove-old-trash-files')


def set_privacy_cleanup(enabled: bool) -> Result:
    value = 'true' if enabled else 'false'
    return _set_bool(
        f'gsettings set {PRIVACY_SCHEMA} remove-old-trash-files {value} && '
        f'gsettings set {PRIVACY_SCHEMA} remove-old-temp-files {value}')
