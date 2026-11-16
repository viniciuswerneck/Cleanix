#!/usr/bin/env python3
""" cleanix - Cleanix, CCleaner-style cleaner for Linux """

import logging
import os
import sys
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk

from . import i18n, settings
from .cleanixwindow import CleanixWindow


def _setup_logging():
    """Grava o log do Cleanix em ~/.local/state/cleanix/cleanix.log."""
    handlers = [logging.StreamHandler(sys.stderr)]
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state'))
    log_file = state / 'cleanix' / 'cleanix.log'
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )


def main():
    _setup_logging()
    config = settings.load_settings()
    i18n.set_language(config.language or i18n.detect_language())
    app = Gtk.Application(application_id='br.cleanix.Cleanix')

    def on_activate():
        win = CleanixWindow(app)
        win.present()

    app.connect('activate', lambda *args: on_activate())
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
