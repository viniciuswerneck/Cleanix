#!/usr/bin/env python3
"""Diálogos do Cleanix: avisos, confirmação, detalhes e histórico."""

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk, Pango

from . import history, systeminfo

CATEGORY_ICONS = {
    'trash': '🗑️',
    'thumbnails': '🖼️',
    'browsers': '🌐',
    'tmp': '🗂️',
    'apt': '📦',
}


def _txt(text, cls=None, wrap=False):
    label = Gtk.Label()
    label.set_text(text)
    label.set_xalign(0.0)
    label.set_halign(Gtk.Align.START)
    if wrap:
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if cls:
        label.add_css_class(cls)
    return label


def _icon(char):
    label = Gtk.Label()
    label.set_text(char)
    label.set_valign(Gtk.Align.CENTER)
    return label


def _vbox(spacing=6):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def _hbox(spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


def _plural(count, singular, plural):
    return f'{count} {singular if count == 1 else plural}'


def show_info(parent, title, message):
    """Mostra um aviso simples, sem bloquear a thread principal."""
    dialog = Gtk.AlertDialog()
    dialog.set_message(title)
    dialog.set_detail(message)
    dialog.set_modal(True)
    dialog.show(parent)


def confirm(parent, title, message, confirm_label, on_confirm):
    """Pede confirmação explícita antes de executar ``on_confirm``."""
    dialog = Gtk.AlertDialog()
    dialog.set_message(title)
    dialog.set_detail(message)
    dialog.set_modal(True)
    dialog.set_buttons(['Cancelar', confirm_label])
    dialog.set_cancel_button(0)
    dialog.set_default_button(1)

    def on_choice(source, result):
        try:
            choice = source.choose_finish(result)
        except GLib.Error:
            return
        if choice == 1:
            on_confirm()

    dialog.choose(parent, None, on_choice)


class DetailsDialog(Gtk.Window):
    """Detalhes por categoria, com seleção compartilhada com a janela."""

    def __init__(self, parent, categories, results, selected, on_clean):
        super().__init__()
        self.set_title('Detalhes da Limpeza')
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(560, -1)
        self.add_css_class('dialog')

        self._results = results
        self._selected = selected
        self._on_clean = on_clean
        self._checks = {}

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt('Detalhes da Limpeza', 'dialog-title'))
        root.append(_txt('Escolha o que deseja remover. As pastas raiz nunca '
                         'são apagadas.', 'muted', wrap=True))

        for cat in categories:
            root.append(self._row(cat))

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        footer = _hbox(10)
        self._total_label = _txt('Total selecionado: 0 B', 'dialog-total')
        self._total_label.set_hexpand(True)
        footer.append(self._total_label)

        cancel = Gtk.Button(label='Cancelar')
        cancel.add_css_class('btn-secondary')
        cancel.connect('clicked', lambda *_: self.close())
        footer.append(cancel)

        clean = Gtk.Button(label='Limpar agora')
        clean.add_css_class('btn-danger')
        clean.connect('clicked', lambda *_: self._clean())
        footer.append(clean)

        root.append(footer)
        self.set_child(root)
        self._update_total()

    def _row(self, cat):
        result = self._results.get(cat.key)
        available = bool(result and result.available) and not cat.requires_admin

        row = _hbox(10)
        row.add_css_class('dialog-row')

        check = Gtk.CheckButton()
        check.set_active(cat.key in self._selected and available)
        check.set_sensitive(available)
        check.set_valign(Gtk.Align.CENTER)
        check.connect('toggled', self._on_toggle, cat.key)
        row.append(check)
        self._checks[cat.key] = check

        row.append(_icon(CATEGORY_ICONS.get(cat.key, '📁')))

        name = _txt(cat.label, 'cat-name')
        name.set_hexpand(True)
        name.set_valign(Gtk.Align.CENTER)
        row.append(name)

        if cat.requires_admin:
            row.append(_txt('Requer administrador', 'muted'))
        elif not available:
            row.append(_txt('Indisponível', 'muted'))
        elif result.files == 0:
            row.append(_txt('Vazio', 'muted'))
        else:
            row.append(_txt(systeminfo.format_bytes(result.bytes), 'cat-size'))
            row.append(_txt(_plural(result.files, 'arquivo', 'arquivos'), 'muted'))

        return row

    def _on_toggle(self, check, key):
        if check.get_active():
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self._update_total()

    def _update_total(self):
        total = 0
        for key, check in self._checks.items():
            if not check.get_active():
                continue
            result = self._results.get(key)
            if result is not None:
                total += result.bytes
        self._total_label.set_text(
            f'Total selecionado: {systeminfo.format_bytes(total)}')

    def _clean(self):
        keys = {key for key, check in self._checks.items()
                if check.get_active() and check.get_sensitive()}
        if not keys:
            show_info(self, 'Nada selecionado',
                      'Marque ao menos uma categoria para limpar.')
            return
        self.close()
        self._on_clean(keys)


class HistoryDialog(Gtk.Window):
    """Lista completa do histórico, com opção de limpar tudo."""

    def __init__(self, parent, entries, on_clear):
        super().__init__()
        self.set_title('Histórico de Limpezas')
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(520, -1)
        self.add_css_class('dialog')

        self._on_clear = on_clear

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt('Histórico de Limpezas', 'dialog-title'))

        if entries:
            for entry in reversed(entries):
                root.append(self._row(entry))
        else:
            root.append(_txt('Nenhuma limpeza registrada ainda', 'empty-text'))

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        footer = _hbox(10)
        clear = Gtk.Button(label='Limpar histórico')
        clear.add_css_class('btn-danger')
        clear.set_sensitive(bool(entries))
        clear.connect('clicked', lambda *_: self._confirm_clear())
        footer.append(clear)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        close = Gtk.Button(label='Fechar')
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        footer.append(close)

        root.append(footer)
        self.set_child(root)

    def _row(self, entry):
        row = _hbox(10)
        row.add_css_class('hist-row')

        check = Gtk.Label()
        check.set_markup('<span foreground="#25CE60">✓</span>')
        check.set_valign(Gtk.Align.CENTER)
        row.append(check)

        info = _vbox(1)
        info.set_hexpand(True)
        info.append(_txt('Limpeza realizada', 'op-title'))
        info.append(_txt(f'Espaço liberado: '
                         f'{systeminfo.format_bytes(entry.bytes)} · '
                         f'{_plural(entry.files, "arquivo", "arquivos")}',
                         'op-sub'))
        row.append(info)

        row.append(_txt(history.format_timestamp(entry.timestamp), 'op-date'))
        return row

    def _confirm_clear(self):
        def do_clear():
            self._on_clear()
            self.close()

        confirm(self, 'Limpar histórico',
                'Todas as entradas serão removidas. Continuar?',
                'Limpar', do_clear)
