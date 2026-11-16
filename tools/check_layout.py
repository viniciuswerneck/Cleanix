#!/usr/bin/env python3
"""Confere a estrutura da tela inicial do Cleanix."""

import sys
import traceback

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

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


app = Gtk.Application(application_id='br.cleanix.CheckLayout')
state = {}


def on_activate(_app):
    win = CleanixWindow(app)
    win.present()
    state['win'] = win

    def check():
        labels = [w for w in walk(win) if isinstance(w, Gtk.Label)]
        state['card_titles'] = [
            label.get_text() for label in labels
            if 'card-title' in label.get_css_classes()
        ]
        state['texts'] = [label.get_text() for label in labels]
        state['checks'] = [w for w in walk(win)
                           if isinstance(w, Gtk.CheckButton)]
        state['review_label'] = win.cleanup_review_btn.get_label()
        state['cpu_now'] = win.cpu_now_label.get_text()
        state['cat_rows'] = sorted(win.cat_rows)
        state['results'] = {k: v.available for k, v in win.results.items()}
        app.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(2800, check)


app.connect('activate', on_activate)
app.run([])

print('resultado:', state)
failures = []
expected = ['Limpeza', 'Memória RAM', 'Uso do Disco', 'Uso de CPU',
            'Últimas Ações']
if errors:
    failures.append(f'{len(errors)} traceback(s)')
if state.get('card_titles') != expected:
    failures.append(f"ordem dos painéis: {state.get('card_titles')}")
if 'O que deseja fazer?' in state.get('texts', []):
    failures.append('bloco "O que deseja fazer?" ainda existe')
if state.get('review_label') != 'Revisar e limpar':
    failures.append(f"botão principal: {state.get('review_label')!r}")
if state.get('checks'):
    failures.append('ainda há checkboxes na tela inicial')
if 'agora' not in state.get('cpu_now', ''):
    failures.append(f"rótulo da CPU: {state.get('cpu_now')!r}")
if state.get('cat_rows') != ['apt', 'browsers', 'thumbnails', 'tmp', 'trash']:
    failures.append(f"categorias: {state.get('cat_rows')}")

if failures:
    print('FALHAS:', '; '.join(failures))
    for error in errors:
        print(error)
    sys.exit(1)
print('OK: tela inicial reorganizada')
