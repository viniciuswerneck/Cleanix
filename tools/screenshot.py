#!/usr/bin/env python3
"""Captura offscreen da janela do Cleanix.

Uso:
    python3 tools/screenshot.py --out /tmp/opencode/cleanix.png
    python3 tools/screenshot.py --out /tmp/opencode/cleanix.png --scroll bottom
"""

import argparse
import sys
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import GLib, Gtk

import cairo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cleanix import i18n  # noqa: E402
from cleanix.cleanixwindow import CleanixWindow  # noqa: E402


def find_scroller(widget):
    """Encontra o primeiro Gtk.ScrolledWindow na árvore."""
    if isinstance(widget, Gtk.ScrolledWindow):
        return widget
    child = widget.get_first_child()
    while child:
        found = find_scroller(child)
        if found:
            return found
        child = child.get_next_sibling()
    return None


def grab(win, out):
    width = win.get_width() or 1536
    height = win.get_height() or 1040

    paintable = Gtk.WidgetPaintable.new(win)
    snapshot = Gtk.Snapshot.new()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    node.draw(cairo.Context(surface))
    surface.write_to_png(str(out))
    print(f'salvo {out} {width}x{height}')


def main():
    parser = argparse.ArgumentParser(description='Captura a janela do Cleanix')
    parser.add_argument('--out', default='/tmp/opencode/cleanix.png',
                        help='arquivo PNG de saída')
    parser.add_argument('--scroll', choices=('top', 'bottom'), default='top',
                        help='posição do conteúdo rolável')
    parser.add_argument('--language', choices=i18n.LANGUAGES, default=None,
                        help='idioma da captura')
    args = parser.parse_args()

    if args.language:
        i18n.set_language(args.language)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    app = Gtk.Application(application_id='br.cleanix.screenshot')

    def on_activate(*_args):
        win = CleanixWindow(app)
        win.present()

        def capture():
            if args.scroll == 'bottom':
                scroller = find_scroller(win)
                if scroller is not None:
                    adj = scroller.get_vadjustment()
                    adj.set_value(adj.get_upper() - adj.get_page_size())
                    GLib.timeout_add(600, do_capture)
                    return False
            do_capture()
            return False

        def do_capture():
            grab(win, out)
            app.quit()
            return False

        GLib.timeout_add(2500, capture)

    app.connect('activate', on_activate)
    return app.run([])


if __name__ == '__main__':
    sys.exit(main())
