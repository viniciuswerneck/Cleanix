#!/usr/bin/env python3
"""Confere a troca de idioma e a reconstrução da janela principal."""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

from cleanix import i18n
from cleanix.cleanixwindow import CleanixWindow

errors = []
original_hook = sys.excepthook


def hook(exc_type, exc, tb):
    errors.append(''.join(traceback.format_exception(exc_type, exc, tb)))
    original_hook(exc_type, exc, tb)


sys.excepthook = hook


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


def side_titles(window):
    return [label.get_text() for label in walk(window)
            if isinstance(label, Gtk.Label)
            and 'side-title' in label.get_css_classes()]


app = Gtk.Application(application_id='br.cleanix.CheckLanguage')
state = {'failures': []}


def expect(condition, message):
    if not condition:
        state['failures'].append(message)


def on_activate(_app):
    window = CleanixWindow(app)
    window.present()
    state['window'] = window
    state['samples'] = []

    def start():
        window._apply_language('en')
        state['samples'].append(len(window._memory_values))
        GLib.timeout_add(2500, check_english)
        return GLib.SOURCE_REMOVE

    def check_english():
        expect(i18n.get_language() == 'en', 'não trocou para inglês')
        titles = side_titles(window)
        for text in ('Cleanup', 'Optimization', 'Adjustments', 'Help & About'):
            expect(text in titles, f'en: falta {text!r} em {titles}')
        expect(len(window._memory_values) > state['samples'][0],
               'gráfico de RAM parou depois da troca para inglês')

        window._apply_language('es')
        expect(i18n.get_language() == 'es', 'não trocou para espanhol')
        titles = side_titles(window)
        for text in ('Limpieza', 'Optimización', 'Ajustes',
                     'Ayuda y Acerca de'):
            expect(text in titles, f'es: falta {text!r} em {titles}')

        window._apply_language('pt_BR')
        expect(i18n.get_language() == 'pt_BR', 'não voltou para português')
        titles = side_titles(window)
        for text in ('Limpeza', 'Otimização', 'Ajustes', 'Ajuda e Sobre'):
            expect(text in titles, f'pt_BR: falta {text!r} em {titles}')

        window._apply_language('fr')
        expect(i18n.get_language() == 'pt_BR',
               'idioma inválido mudou o idioma atual')

        GLib.timeout_add(2500, finish)
        return GLib.SOURCE_REMOVE

    def finish():
        expect(len(window._memory_values) > state['samples'][0],
               'gráfico de RAM parou no fim das trocas')
        app.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(2800, start)


app.connect('activate', on_activate)
app.run([])

failures = state['failures'] + [f'{len(errors)} traceback(s)'] * bool(errors)
if failures:
    print('FALHAS:', '; '.join(failures))
    for error in errors:
        print(error)
    sys.exit(1)
print('OK: idiomas trocados e janela reconstruída')
