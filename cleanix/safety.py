#!/usr/bin/env python3
""" Safety module for cleanix application """

import os
import shutil
import subprocess
import warnings
from gi.repository import Gtk

# Critical systems that should NOT be automatically modified
PROTECTED_PATHS = [
    '/etc/',
    '/usr/',
    '/var/',
    '/boot/',
    '/proc/',
    '/sys/',
    '/bin/',
    '/sbin/',
    '/lib/',
]

# Protected file extensions and patterns
PROTECTED_EXTENSIONS = [
    '.py',
    '.conf',
    '.service',
    '.target',
    '.mount',
]

# Track operations for undo/redo
operation_log = []


def validate_path_safety(path):
    """Validate that a path is safe to operate on.
    
    Returns True if safe, False if path is protected.
    """
    abs_path = os.path.abspath(path)
    
    for protected in PROTECTED_PATHS:
        if abs_path.startswith(protected + os.sep) or abs_path == protected:
            return False, f"Caminho protegido: {protected}"
    
    # Check for sensitive files
    risky_patterns = ['fstab', 'grub', 'boot', 'root']
    path_lower = abs_path.lower()
    for pattern in risky_patterns:
        if pattern in path_lower:
            return False, f"Caminho sensível detectado: {pattern}"
    
    return True, ""


def safe_remove(path, dry_run=False):
    """Safely remove a file or directory with validation.
    
    Args:
        path: Path to remove
        dry_run: If True, only simulate the removal
    
    Returns:
        (success: bool, message: str)
    """
    if dry_run:
        return True, f"[DRY RUN] Remover-ia: {path}"
    
    # Validate safety
    is_safe, reason = validate_path_safety(path)
    if not is_safe:
        return False, f"Não seguro: {reason}"
    
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
            return True, f"Removido: {path}"
        elif os.path.isdir(path):
            shutil.rmtree(path)
            return True, f"Removido diretório: {path}"
        else:
            return False, f"Caminho não existe: {path}"
    except Exception as e:
        return False, f"Erro ao remover {path}: {str(e)}"


def safe_execute_command(command, dry_run=False, timeout=60):
    """Safely execute a system command.
    
    Args:
        command: List of command arguments
        dry_run: If True, only simulate
        timeout: Timeout in seconds
    
    Returns:
        (success: bool, output: str, error: str)
    """
    if dry_run:
        return True, "Simulação de comando: " + " ".join(command), ""
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout, result.stderr
        else:
            return False, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Comando excedeu o tempo limite"
    except Exception as e:
        return False, "", str(e)


def show_confirmation_dialog(parent, title, message, yes_label="Confirmar", no_label="Cancelar"):
    """Show a confirmation dialog with safety warning.
    
    Returns True if user confirms, False otherwise.
    """
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        message=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.NO,
        text=title,
    )
    dialog.set_markup(f'<b>{message}</b>')
    
    # Add custom buttons
    btn_yes = Gtk.Button.new_with_label(yes_label)
    btn_yes.get_style_context().add_class('destructive-action')
    btn_no = dialog.get_action_widget()
    btn_no.set_label(no_label)
    
    dialog.add_action_widget(btn_yes, 0)
    dialog.add_action_widget(btn_no, 1)
    
    response = dialog.run()
    dialog.destroy()
    
    return response == 0


def log_operation(operation, details, success=True):
    """Log an operation for undo/redo functionality.
    
    Args:
        operation: Description of the operation
        details: Additional details
        success: Whether the operation succeeded
    """
    entry = {
        'operation': operation,
        'details': details,
        'success': success,
    }
    operation_log.append(entry)
    return entry


def get_operation_log():
    """Get the current operation log for undo/redo."""
    return operation_log.copy()


def clear_operation_log():
    """Clear the operation log."""
    operation_log.clear()