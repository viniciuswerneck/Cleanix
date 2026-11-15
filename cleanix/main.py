#!/usr/bin/env python3
""" cleanix - Cleanix, CCleaner-style cleaner for Linux """

import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk

from .cleanixwindow import CleanixWindow


def main():
    app = Gtk.Application(application_id='br.cleanix.Cleanix')

    def on_activate():
        win = CleanixWindow(app)
        win.present()

    app.connect('activate', lambda *args: on_activate())
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
