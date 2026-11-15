#!/usr/bin/env python3
""" Utility functions for cleanix application """

import os
import glob
import subprocess
import json
from gi.repository import Gtk, Gdk

# Directories commonly cleaned by cleanix
TEMP_DIRS = [
    os.path.expanduser('~/tmp'),
    '/tmp',
    os.path.expanduser('~/.cache'),
    os.path.expanduser('~/.local/share/Trash'),
    os.path.expanduser('~/.cache/thumbnails'),
    '/var/cache/apt/archives',
    '/var/cache/apt/srcpkg',
]

BROWSER_CACHE_DIRS = {
    'chrome': os.path.expanduser('~/.cache/google-chrome'),
    'firefox': os.path.expanduser('~/.mozilla/firefox'),
    'chromium': os.path.expanduser('~/.cache/chromium'),
}

SYSTEM_JUNK_PATTERNS = [
    '*.tmp',
    '*.temp',
    '*~',  # backup files
    '*.log.1',
    '*.log.old',
]


def get_disk_usage():
    """Get disk usage statistics.
    
    Returns:
        dict with total, used, free in GB
    """
    try:
        stat = os.statvfs('/')
        total = stat.f_frsize * stat.f_blocks / (1024**3)
        used = stat.f_frsize * (stat.f_blocks - stat.f_bfree) / (1024**3)
        free = stat.f_frsize * stat.f_avail / (1024**3)
        return {
            'total': round(total, 2),
            'used': round(used, 2),
            'free': round(free, 2),
        }
    except Exception:
        return {'total': 0, 'used': 0, 'free': 0}


def get_temp_files_scanner(dry_run=True):
    """Scan for temporary files across common locations.
    
    Args:
        dry_run: If True, only scan without deleting
    
    Returns:
        list of dicts with file path, size, category
    """
    files_found = []
    
    for temp_dir in TEMP_DIRS:
        if not os.path.exists(temp_dir):
            continue
        
        try:
            for root, dirs, files in os.walk(temp_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        size = os.path.getsize(fpath)
                        # Determine category based on path
                        category = categorize_file(fpath)
                        files_found.append({
                            'path': fpath,
                            'size': size,
                            'category': category,
                            'size_formatted': format_size(size),
                        })
                    except OSError:
                        continue
        except PermissionError:
            continue
        except Exception:
            continue
    
    # Sort by size, largest first
    files_found.sort(key=lambda x: x['size'], reverse=True)
    return files_found


def categorize_file(filepath):
    """Categorize a file for chart visualization.
    
    Returns:
        Category string: 'cache', 'log', 'trash', 'browser', 'other'
    """
    lower = filepath.lower()
    
    # Browser caches
    if 'google-chrome' in lower or 'chromium' in lower or 'firefox' in lower:
        return 'browser'
    
    # Thumbnail cache
    if 'thumbnails' in lower:
        return 'thumbnail'
    
    # APT cache
    if 'apt' in lower or '/var/cache/apt' in lower:
        return 'apt-cache'
    
    # User cache
    if '/cache' in lower:
        return 'cache'
    
    # Trash
    if 'trash' in lower or 'tmp' in lower:
        return 'trash'
    
    return 'other'


def format_size(size_bytes):
    """Format size in bytes to human-readable format."""
    if size_bytes == 0:
        return '0 B'
    
    size_name = ('B', 'KB', 'MB', 'GB', 'TB')
    i = int(abs(size_bytes).bit_length() / 10)
    i = min(i, len(size_name) - 1)
    p = 2 ** (i * 10)
    s = round(size_bytes / p, 2)
    return f'{s} {size_name[i]}'


def get_browser_cache_sizes(dry_run=True):
    """Get sizes of browser caches.
    
    Returns:
        dict with browser names and their cache sizes
    """
    sizes = {}
    
    for browser, path in BROWSER_CACHE_DIRS.items():
        if not os.path.exists(path):
            sizes[browser] = {'size': 0, 'formatted': '0 B', 'items': 0}
            continue
        
        total_size = 0
        item_count = 0
        
        try:
            for root, dirs, files in os.walk(path):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        total_size += os.path.getsize(fpath)
                        item_count += 1
                    except OSError:
                        continue
        except PermissionError:
            pass
        
        sizes[browser] = {
            'size': total_size,
            'formatted': format_size(total_size),
            'items': item_count,
        }
    
    return sizes


def check_apt_cache():
    """Check APT cache size.
    
    Returns:
        dict with cache size info
    """
    try:
        result = subprocess.run(
            ['du', '-sh', '/var/cache/apt/archives/'],
            capture_output=True,
            text=True,
        )
        size_str = result.stdout.strip()
        
        # Parse human-readable size
        sizes = {
            'size': 0,
            'formatted': '0 B',
            'detail': size_str,
        }
        return sizes
    except Exception:
        return {'size': 0, 'formatted': '0 B', 'detail': 'Erro ao verificar'}


def get_system_info():
    """Get general system information for the welcome/dashboard screen.
    
    Returns:
        dict with system info
    """
    import platform
    
    disk = get_disk_usage()
    
    return {
        'os': platform.system(),
        'os_version': platform.version(),
        'python': platform.python_version(),
        'architecture': platform.machine(),
        'disk_total': disk['total'],
        'disk_used': disk['used'],
        'disk_free': disk['free'],
    }


def export_report(data):
    """Export a cleaning report to JSON file.
    
    Args:
        data: Report data dict
    
    Returns:
        Path to exported file or None on error
    """
    try:
        dialog = Gtk.FileChooserNative(
            title='Salvar Relatório',
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.set_current_name('cleanix-relatorio.json')
        
        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            filepath = dialog.get_filename()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            dialog.destroy()
            return filepath
        
        dialog.destroy()
        return None
    except Exception as e:
        print(f"Erro ao exportar relatório: {e}")
        return None