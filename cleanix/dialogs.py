#!/usr/bin/env python3
"""Diálogos do Cleanix: avisos, confirmação, detalhes e histórico."""

import logging
import threading
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from . import (adjustments, autostart, history, i18n, memory, settings,
               systeminfo, xray)
from .execution import Result, execute_command
import re

log = logging.getLogger(__name__)

STARTUP_COLUMNS = 4

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
    dialog.set_buttons([i18n.t('common.cancel'), confirm_label])
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


def _limit(text, size=1500):
    if len(text) <= size:
        return text
    return text[:size] + '\n…'


def help_about_text() -> tuple[str, str]:
    """Título e corpo do diálogo único de Ajuda e Sobre."""
    body = i18n.t('help.body')
    body += '\n\n' + i18n.t('about.version')
    body += '\n' + i18n.t('about.distro',
                          name=systeminfo.distro_name())
    return i18n.t('help.title'), body


def startup_content_limit(screen_height, reserved=320):
    """Altura máxima da lista de Startup Apps para caber na tela."""
    return max(160, min(340, screen_height - reserved))


class DetailsDialog(Gtk.Window):
    """Detalhes por categoria, com seleção compartilhada com a janela."""

    def __init__(self, parent, categories, results, selected, on_clean):
        super().__init__()
        self.set_title(i18n.t('details.title'))
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

        root.append(_txt(i18n.t('details.title'), 'dialog-title'))
        root.append(_txt(i18n.t('details.subtitle'), 'muted', wrap=True))

        for cat in categories:
            root.append(self._row(cat))

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        footer = _hbox(10)
        self._total_label = _txt(
            i18n.t('details.total', value=systeminfo.format_bytes(0)),
            'dialog-total')
        self._total_label.set_hexpand(True)
        footer.append(self._total_label)

        cancel = Gtk.Button(label=i18n.t('common.cancel'))
        cancel.add_css_class('btn-secondary')
        cancel.connect('clicked', lambda *_: self.close())
        footer.append(cancel)

        clean = Gtk.Button(label=i18n.t('details.clean'))
        clean.add_css_class('btn-danger')
        clean.connect('clicked', lambda *_: self._clean())
        footer.append(clean)

        root.append(footer)
        self.set_child(root)
        self._update_total()

    def _row(self, cat):
        result = self._results.get(cat.key)
        available = bool(result and result.available)

        row = _hbox(10)
        row.add_css_class('dialog-row')

        check = Gtk.CheckButton()
        check.set_active(cat.key in self._selected and available)
        check.set_sensitive(available)
        check.set_valign(Gtk.Align.CENTER)
        if cat.requires_admin:
            check.set_tooltip_text(i18n.t('details.admin_tooltip'))
        check.connect('toggled', self._on_toggle, cat.key)
        row.append(check)
        self._checks[cat.key] = check

        row.append(_icon(CATEGORY_ICONS.get(cat.key, '📁')))

        name = _txt(i18n.t(f'category.{cat.key}'), 'cat-name')
        name.set_hexpand(True)
        name.set_valign(Gtk.Align.CENTER)
        row.append(name)

        if not available:
            row.append(_txt(i18n.t('details.unavailable'), 'muted'))
        elif result.files == 0 and result.bytes == 0:
            row.append(_txt(i18n.t('details.empty'), 'muted'))
        else:
            row.append(_txt(systeminfo.format_bytes(result.bytes), 'cat-size'))
            if result.files:
                row.append(_txt(i18n.tn('history.files', result.files),
                                'muted'))

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
            i18n.t('details.total', value=systeminfo.format_bytes(total)))

    def _clean(self):
        keys = {key for key, check in self._checks.items()
                if check.get_active() and check.get_sensitive()}
        if not keys:
            show_info(self, i18n.t('clean.none.title'),
                      i18n.t('details.none.body'))
            return
        self.close()
        self._on_clean(keys)


class _ActionDialog(Gtk.Window):
    """Base para diálogos que executam comandos do sistema."""

    heading_key = ''
    subtitle_key = ''
    actions = ()

    def __init__(self, parent, on_done=None):
        super().__init__()
        self._buttons = {}
        self._on_done = on_done
        heading = i18n.t(self.heading_key)
        self.set_title(heading)
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(560, -1)
        self.add_css_class('dialog')

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(heading, 'dialog-title'))
        if self.subtitle_key:
            root.append(_txt(i18n.t(self.subtitle_key), 'muted', wrap=True))

        for action in self.actions:
            root.append(self._action_row(action))

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        self.status = _txt('', 'muted', wrap=True)
        self.status.set_visible(False)
        root.append(self.status)

        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        root.append(close)

        self.set_child(root)

    def _action_row(self, action):
        row = _hbox(10)
        row.add_css_class('dialog-row')

        button = Gtk.Button(label=i18n.t(action['label_key']))
        button.add_css_class('btn-green')
        if action.get('dialog') is not None:
            button.connect('clicked', lambda *_: action['dialog'](self))
        else:
            button.connect('clicked', self._on_clicked, action)
        row.append(button)
        self._buttons[action['label_key']] = button

        description = _txt(i18n.t(action['description_key']), 'cat-name')
        description.set_hexpand(True)
        description.set_valign(Gtk.Align.CENTER)
        description.set_wrap(True)
        row.append(description)
        return row

    def _on_clicked(self, button, action):
        label = i18n.t(action['label_key'])
        log.info('Ação escolhida: %s', label)
        confirm(self, i18n.t('action.confirm.title', label=label),
                i18n.t(action['detail_key']),
                i18n.t('action.confirm.button'),
                lambda: self._start(button, action))

    def _start(self, button, action):
        label = i18n.t(action['label_key'])
        button.set_label(i18n.t('action.running'))
        button.set_sensitive(False)
        self.status.set_text(i18n.t('action.status.running', label=label))

        def work():
            result = execute_command(action['command'], action['as_root'])
            GLib.idle_add(self._done, button, action, result)

        threading.Thread(target=work, daemon=True, name='cleanix-action').start()

    def _done(self, button, action, result):
        label = i18n.t(action['label_key'])
        button.set_label(label)
        button.set_sensitive(True)

        if result.ok:
            self.status.set_text(i18n.t('action.status.done', label=label))
            body = result.output or i18n.t('action.done.body')
            show_info(self, i18n.t('action.done.title', label=label),
                      _limit(body))
            if self._on_done is not None:
                self._on_done()
        else:
            self.status.set_text(i18n.t('action.status.failed', label=label))
            show_info(self, i18n.t('action.failed.title', label=label),
                      _limit(result.error or i18n.t('action.failed.body')))
        return GLib.SOURCE_REMOVE


OPTIMIZER_ACTIONS = (
    {
        'label_key': 'optimizer.apt.label',
        'description_key': 'optimizer.apt.description',
        'detail_key': 'optimizer.apt.detail',
        'command': 'apt-get autoremove -y && apt-get clean',
        'as_root': True,
    },
    {
        'label_key': 'optimizer.journal.label',
        'description_key': 'optimizer.journal.description',
        'detail_key': 'optimizer.journal.detail',
        'command': 'journalctl --vacuum-time=7d',
        'as_root': True,
    },
    {
        'label_key': 'optimizer.fstrim.label',
        'description_key': 'optimizer.fstrim.description',
        'detail_key': 'optimizer.fstrim.detail',
        'command': 'fstrim -av',
        'as_root': True,
    },
)


class StartupAppsDialog(Gtk.Window):
    """Ativa e desativa os aplicativos que iniciam junto com o sistema."""

    def __init__(self, parent):
        super().__init__()
        self.set_title(i18n.t('startup.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        width, _height = self._screen_size()
        self.set_default_size(min(1020, max(520, width - 80)), -1)
        self.add_css_class('dialog')

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(i18n.t('startup.title'), 'dialog-title'))
        root.append(_txt(i18n.t('startup.subtitle'), 'muted', wrap=True))

        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(10)
        self._grid.set_row_spacing(8)
        self._grid.set_column_homogeneous(True)
        self._grid.set_margin_top(2)
        self._grid.set_margin_bottom(2)

        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.NEVER,
                                  Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_child(self._grid)
        self._scroller.set_propagate_natural_height(True)
        self._scroller.set_max_content_height(self._content_limit())
        self._scroller.set_vexpand(True)
        root.append(self._scroller)

        self.status = _txt('', 'muted', wrap=True)
        root.append(self.status)

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        root.append(close)

        self.set_child(root)

        # Esc sempre fecha, mesmo que a lista cresça.
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._on_key)
        self.add_controller(keys)

        self._restoring = False
        self._entries = []
        self._load()

    @staticmethod
    def _screen_size():
        display = Gdk.Display.get_default()
        if display is not None:
            monitors = display.get_monitors()
            if monitors.get_n_items():
                geometry = monitors.get_item(0).get_geometry()
                return geometry.width, geometry.height
        return 1280, 800

    def _content_limit(self):
        _width, height = self._screen_size()
        return startup_content_limit(height)

    def _on_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _clear(self):
        while True:
            child = self._grid.get_first_child()
            if child is None:
                break
            self._grid.remove(child)

    def _load(self):
        self._clear()
        try:
            self._entries = autostart.list_entries(Path.home())
        except OSError as exc:
            log.exception('Falha ao listar aplicativos de inicialização')
            self._entries = []
            show_info(self, i18n.t('startup.error.title'),
                      i18n.t('startup.error.body', detail=exc))

        if not self._entries:
            self._grid.attach(
                _txt(i18n.t('startup.empty'), 'empty-text'),
                0, 0, STARTUP_COLUMNS, 1)
            return

        for index, entry in enumerate(self._entries):
            self._grid.attach(self._cell(entry),
                              index % STARTUP_COLUMNS,
                              index // STARTUP_COLUMNS, 1, 1)

    def _cell(self, entry):
        cell = _hbox(8)
        cell.add_css_class('dialog-row')

        switch = Gtk.Switch()
        switch.set_active(not entry.hidden)
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect('notify::active', self._on_toggle, entry)
        cell.append(switch)

        label = _txt(entry.name, 'cat-name', wrap=True)
        label.set_lines(2)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        cell.append(label)

        if entry.command:
            cell.set_tooltip_text(entry.command)
        return cell

    def _on_toggle(self, switch, _pspec, entry):
        if self._restoring:
            return
        enabled = switch.get_active()
        try:
            autostart.set_enabled(entry, enabled, Path.home())
        except OSError as exc:
            log.exception('Falha ao alterar o aplicativo %s', entry.name)
            show_info(self, i18n.t('startup.change_error.title'),
                      i18n.t('startup.change_error.body', name=entry.name,
                             detail=exc))
            self._restoring = True
            switch.set_active(not enabled)
            self._restoring = False
            return

        estado = i18n.t('startup.enabled' if enabled else 'startup.disabled')
        log.info('Startup %s: %s', entry.name, estado)
        self.status.set_text(
            i18n.t('startup.status', name=entry.name, state=estado))


class MemoryDialog(Gtk.Window):
    """Libera o cache de arquivos da memória RAM, fora da limpeza."""

    def __init__(self, parent, on_released=None):
        super().__init__()
        self._on_released = on_released
        self.set_title(i18n.t('memory.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(520, -1)
        self.add_css_class('dialog')

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        heading = _hbox(8)
        heading.append(_icon('🧠'))
        heading.append(_txt(i18n.t('memory.title'), 'dialog-title'))
        root.append(heading)

        root.append(_txt(i18n.t('memory.explain'), 'muted', wrap=True))

        self._cache_label = _txt(
            i18n.t('memory.cache_in_use', value='—'), 'cat-name')
        root.append(self._cache_label)

        self._free_label = _txt('', 'muted', wrap=True)
        root.append(self._free_label)

        self.status = _txt('', 'muted', wrap=True)
        root.append(self.status)

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        footer = _hbox(10)
        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        footer.append(close)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        self._release = Gtk.Button(label=i18n.t('memory.release'))
        self._release.add_css_class('btn-green')
        self._release.connect('clicked', self._on_release)
        footer.append(self._release)

        root.append(footer)
        self.set_child(root)
        self._refresh()

    def _refresh(self):
        values = memory.read_meminfo()
        if not values:
            self._cache_label.set_text(i18n.t('memory.unavailable'))
            self._free_label.set_text('')
            self._release.set_sensitive(False)
            return

        cache = memory.reclaimable_memory(values)
        self._cache_label.set_text(
            i18n.t('memory.cache_in_use',
                   value=systeminfo.format_bytes(cache)))
        self._free_label.set_text(i18n.t('memory.max_release'))
        self._release.set_sensitive(True)

    def _on_release(self, _button):
        confirm(self, i18n.t('memory.confirm.title'),
                i18n.t('memory.confirm.body'),
                i18n.t('memory.confirm.action'), self._start)

    def _start(self):
        self._release.set_label(i18n.t('memory.releasing'))
        self._release.set_sensitive(False)
        self.status.set_text(i18n.t('memory.releasing_status'))
        threading.Thread(target=self._work, daemon=True,
                         name='cleanix-memory').start()

    def _work(self):
        result = memory.release_memory()
        GLib.idle_add(self._done, result)

    def _done(self, result):
        self._release.set_label(i18n.t('memory.release'))
        self._release.set_sensitive(True)

        if result.ok:
            self.status.set_text(i18n.t('memory.released'))
            show_info(self, i18n.t('memory.title'), result.output)
            self._refresh()
            if self._on_released is not None:
                self._on_released()
        else:
            self.status.set_text(i18n.t('memory.failed_status'))
            show_info(self, i18n.t('memory.title'),
                      result.error or i18n.t('memory.failed_body'))
        return GLib.SOURCE_REMOVE


class OptimizerDialog(_ActionDialog):
    """Otimizador do sistema, com ações que realmente são executadas."""

    heading_key = 'optimizer.title'
    subtitle_key = 'optimizer.subtitle'
    actions = OPTIMIZER_ACTIONS + (
        {
            'label_key': 'optimizer.memory.label',
            'description_key': 'optimizer.memory.description',
            'dialog': lambda parent: MemoryDialog(parent).present(),
        },
        {
            'label_key': 'optimizer.startup.label',
            'description_key': 'optimizer.startup.description',
            'dialog': lambda parent: StartupAppsDialog(parent).present(),
        },
    )


class AdjustmentsDialog(Gtk.Window):
    """Ajustes do sistema com switches reais (gsettings, sem root)."""

    def __init__(self, parent):
        super().__init__()
        self.set_title(i18n.t('adjust.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(560, -1)
        self.add_css_class('dialog')

        self._restoring = True

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(i18n.t('adjust.title'), 'dialog-title'))
        root.append(_txt(i18n.t('adjust.subtitle'), 'muted', wrap=True))

        animations = adjustments.get_animations()
        privacy = adjustments.get_privacy_cleanup()

        self._animations_switch = self._make_switch(animations)
        self._animations_switch.connect('notify::active',
                                        self._on_animations)
        root.append(self._row(i18n.t('adjust.animations.title'),
                              i18n.t('adjust.animations.desc'),
                              self._animations_switch))

        self._privacy_switch = self._make_switch(privacy)
        self._privacy_switch.connect('notify::active', self._on_privacy)
        root.append(self._row(i18n.t('adjust.privacy.title'),
                              i18n.t('adjust.privacy.desc'),
                              self._privacy_switch))

        self.status = _txt('', 'muted', wrap=True)
        if animations is None and privacy is None:
            self.status.set_text(i18n.t('adjust.unavailable'))
        root.append(self.status)

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        root.append(close)

        self.set_child(root)
        self._restoring = False

    @staticmethod
    def _make_switch(state):
        switch = Gtk.Switch()
        switch.set_active(bool(state))
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_sensitive(state is not None)
        return switch

    def _row(self, title, description, switch):
        row = _hbox(12)
        row.add_css_class('dialog-row')

        info = _vbox(1)
        info.set_hexpand(True)
        info.append(_txt(title, 'cat-name'))
        info.append(_txt(description, 'muted', wrap=True))
        row.append(info)
        row.append(switch)
        return row

    def _apply(self, switch, enabled, setter):
        if self._restoring:
            return
        result = setter(enabled)
        if result.ok:
            self.status.set_text(i18n.t('adjust.saved'))
            return
        self._restoring = True
        switch.set_active(not enabled)
        self._restoring = False
        self.status.set_text(
            i18n.t('adjust.error', detail=result.error))

    def _on_animations(self, switch, _pspec):
        self._apply(switch, switch.get_active(), adjustments.set_animations)

    def _on_privacy(self, switch, _pspec):
        self._apply(switch, switch.get_active(),
                    adjustments.set_privacy_cleanup)


class SettingsDialog(Gtk.Window):
    """Preferências do Cleanix, salvas assim que mudam."""

    def __init__(self, parent, on_language_changed=None):
        super().__init__()
        self.set_title(i18n.t('settings.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(520, -1)
        self.add_css_class('dialog')

        self._settings = settings.load_settings()
        self._on_language_changed = on_language_changed
        self._recording = True

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(i18n.t('settings.title'), 'dialog-title'))
        root.append(_txt(i18n.t('settings.subtitle'), 'muted', wrap=True))

        self._language_dropdown = Gtk.DropDown.new_from_strings(
            [i18n.LANGUAGE_NAMES[code] for code in i18n.LANGUAGES])
        self._language_dropdown.set_selected(
            i18n.LANGUAGES.index(i18n.get_language()))
        self._language_dropdown.set_valign(Gtk.Align.CENTER)
        self._language_dropdown.connect('notify::selected',
                                        self._on_language)
        root.append(self._row(
            i18n.t('settings.language.title'),
            i18n.t('settings.language.desc'), self._language_dropdown))

        self._confirm_switch = Gtk.Switch()
        self._confirm_switch.set_active(
            self._settings.confirm_before_clean)
        self._confirm_switch.set_valign(Gtk.Align.CENTER)
        self._confirm_switch.connect('notify::active', self._on_toggle)
        root.append(self._row(
            i18n.t('settings.confirm.title'),
            i18n.t('settings.confirm.desc'), self._confirm_switch))

        self._history_switch = Gtk.Switch()
        self._history_switch.set_active(self._settings.keep_history)
        self._history_switch.set_valign(Gtk.Align.CENTER)
        self._history_switch.connect('notify::active', self._on_toggle)
        root.append(self._row(
            i18n.t('settings.history.title'),
            i18n.t('settings.history.desc'), self._history_switch))

        self.status = _txt('', 'muted', wrap=True)
        root.append(self.status)

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        root.append(close)

        self.set_child(root)
        self._recording = False

    def _row(self, title, description, control):
        row = _hbox(12)
        row.add_css_class('dialog-row')

        info = _vbox(1)
        info.set_hexpand(True)
        info.append(_txt(title, 'cat-name'))
        info.append(_txt(description, 'muted', wrap=True))
        row.append(info)
        row.append(control)
        return row

    def _on_toggle(self, _switch, _pspec):
        if self._recording:
            return
        self._settings = settings.Settings(
            confirm_before_clean=self._confirm_switch.get_active(),
            keep_history=self._history_switch.get_active(),
            language=self._settings.language,
        )
        try:
            settings.save_settings(self._settings)
        except OSError as exc:
            log.exception('Falha ao salvar as configurações')
            show_info(self, i18n.t('settings.save_error.title'),
                      i18n.t('settings.save_error.body', detail=exc))
            self.status.set_text(i18n.t('settings.save_failed'))
            return
        self.status.set_text(i18n.t('settings.saved'))

    def _on_language(self, dropdown, _pspec):
        if self._recording:
            return
        index = dropdown.get_selected()
        if index < 0 or index >= len(i18n.LANGUAGES):
            return
        code = i18n.LANGUAGES[index]
        if code == i18n.get_language():
            return

        new_settings = settings.Settings(
            confirm_before_clean=self._confirm_switch.get_active(),
            keep_history=self._history_switch.get_active(),
            language=code,
        )
        try:
            settings.save_settings(new_settings)
        except OSError as exc:
            log.exception('Falha ao salvar o idioma')
            show_info(self, i18n.t('settings.save_error.title'),
                      i18n.t('settings.save_error.body', detail=exc))
            self.status.set_text(i18n.t('settings.save_failed'))
            self._recording = True
            dropdown.set_selected(
                i18n.LANGUAGES.index(i18n.get_language()))
            self._recording = False
            return

        self._settings = new_settings
        if self._on_language_changed is not None:
            self._on_language_changed(code)
        self.close()


class HistoryDialog(Gtk.Window):
    """Lista completa do histórico, com opção de limpar tudo."""

    def __init__(self, parent, entries, on_clear):
        super().__init__()
        self.set_title(i18n.t('history.dialog.title'))
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

        root.append(_txt(i18n.t('history.dialog.title'), 'dialog-title'))

        if entries:
            for entry in reversed(entries):
                root.append(self._row(entry))
        else:
            root.append(_txt(i18n.t('history.empty'), 'empty-text'))

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        footer = _hbox(10)
        clear = Gtk.Button(label=i18n.t('history.clear'))
        clear.add_css_class('btn-danger')
        clear.set_sensitive(bool(entries))
        clear.connect('clicked', lambda *_: self._confirm_clear())
        footer.append(clear)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        close = Gtk.Button(label=i18n.t('common.close'))
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
        info.append(_txt(i18n.t('history.entry'), 'op-title'))
        info.append(_txt(
            i18n.t('history.entry_sub',
                   size=systeminfo.format_bytes(entry.bytes),
                   files=i18n.tn('history.files', entry.files)),
            'op-sub'))
        row.append(info)

        row.append(_txt(history.format_timestamp(entry.timestamp), 'op-date'))
        return row

    def _confirm_clear(self):
        def do_clear():
            self._on_clear()
            self.close()

        confirm(self, i18n.t('history.clear.confirm.title'),
                i18n.t('history.clear.confirm.body'),
                i18n.t('history.clear.confirm.action'), do_clear)


class SmartHealthDialog(Gtk.Window):
    """Verificação SMART sob demanda para um disco físico."""

    def __init__(self, parent, disk_name, disk_model=''):
        super().__init__()
        self.disk_name = disk_name
        self.disk_model = disk_model or disk_name
        self.set_title(i18n.t('smart.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(620, 420)
        self.add_css_class('dialog')
        self.add_css_class('smart-dialog')

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        heading = _hbox(8)
        heading.append(_icon('💽'))
        heading.append(_txt(i18n.t('smart.title'), 'dialog-title'))
        root.append(heading)

        root.append(_txt(i18n.t('smart.disk_label',
                                disk=f'{disk_name} · {self.disk_model}'),
                         'cat-name'))
        root.append(_txt(i18n.t('smart.subtitle'), 'muted', wrap=True))

        self.overall_label = _txt('', 'cat-name')
        self.overall_label.set_wrap(True)
        root.append(self.overall_label)

        self.attrs_label = _txt('', 'muted', wrap=True)
        root.append(self.attrs_label)

        self.details_label = _txt('', 'muted', wrap=True)
        self.details_label.set_selectable(True)
        root.append(self.details_label)

        self.status = _txt('', 'muted', wrap=True)
        root.append(self.status)

        sep = Gtk.Separator()
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        root.append(sep)

        footer = _hbox(10)
        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        footer.append(close)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        self.install_btn = Gtk.Button(label=i18n.t('smart.install'))
        self.install_btn.add_css_class('btn-secondary')
        self.install_btn.set_visible(False)
        self.install_btn.connect('clicked', lambda *_: self._start_install())
        footer.append(self.install_btn)

        self.check_btn = Gtk.Button(label=i18n.t('disks.smart_check'))
        self.check_btn.add_css_class('btn-green')
        self.check_btn.connect('clicked', lambda *_: self._start())
        footer.append(self.check_btn)

        root.append(footer)
        self.set_child(root)

        # inicia verificação automaticamente ao abrir
        GLib.idle_add(self._start)

    def _start(self):
        if not self.check_btn.get_sensitive():
            return False
        self.check_btn.set_sensitive(False)
        self._set_install_visible(False)
        self.status.set_text(i18n.t('smart.running'))
        self.overall_label.set_text('')
        self.attrs_label.set_text('')
        self.details_label.set_text('')
        threading.Thread(target=self._work, daemon=True,
                         name='cleanix-smart').start()
        return False

    def _set_install_visible(self, visible):
        if hasattr(self, 'install_btn'):
            self.install_btn.set_visible(visible)
            self.install_btn.set_sensitive(visible)

    def _work(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', self.disk_name or ''):
            GLib.idle_add(self._done_missing, i18n.t('smart.error'),
                          i18n.t('smart.invalid_disk'), False)
            return
        if not systeminfo.smartctl_available():
            GLib.idle_add(self._done_missing,
                          i18n.t('smart.not_installed.title'),
                          i18n.t('smart.not_installed.body'), True)
            return
        cmd = f'smartctl -H -A /dev/{self.disk_name}'
        result = execute_command(cmd, as_root=True)
        parsed = systeminfo.parse_smartctl(
            (result.output or '') + '\n' + (result.error or ''))
        GLib.idle_add(self._done, result, parsed)

    def _done_missing(self, title, body, can_install=False):
        self.check_btn.set_sensitive(True)
        self.status.set_text('')
        self.overall_label.set_text(title)
        self.details_label.set_text(body)
        self._set_install_visible(bool(can_install))
        return GLib.SOURCE_REMOVE

    def _start_install(self):
        if not self.install_btn.get_sensitive():
            return
        self.install_btn.set_sensitive(False)
        self.check_btn.set_sensitive(False)
        self.status.set_text(i18n.t('smart.installing'))
        threading.Thread(target=self._install_work, daemon=True,
                         name='cleanix-smart-install').start()

    def _install_work(self):
        cmd = 'apt-get install -y smartmontools'
        result = execute_command(cmd, as_root=True)
        GLib.idle_add(self._install_done, result)

    def _install_done(self, result):
        self.check_btn.set_sensitive(True)
        if result.ok and systeminfo.smartctl_available():
            self.status.set_text(i18n.t('smart.installed'))
            # tenta verificar automaticamente
            self._start()
        else:
            self.install_btn.set_sensitive(True)
            self.status.set_text(i18n.t('smart.install_failed'))
            msg = self.details_label.get_text() or ''
            err = _limit(result.error) if not result.ok else ''
            extra = err or ('' if systeminfo.smartctl_available() else i18n.t('smart.not_installed.body'))
            if extra and extra not in msg:
                self.details_label.set_text((msg + '\n\n' + extra).strip())
        return GLib.SOURCE_REMOVE

    def _done(self, result, parsed):
        self.check_btn.set_sensitive(True)
        overall = parsed.get('overall', 'unknown')
        overall_text = parsed.get('overall_text') or i18n.t(
            f'smart.overall.{overall}')
        self.overall_label.set_text(overall_text)
        attrs = parsed.get('attributes') or []
        # prioriza atributos críticos
        important = [a for a in attrs if a.get('critical')]
        lines = []
        if important:
            lines.append(i18n.t('smart.attrs_title'))
            for a in important:
                lines.append(f"- {a.get('name')}: {a.get('raw', a.get('value', ''))}")
        else:
            # mostra alguns atributos se houver
            if attrs:
                lines.append(i18n.t('smart.attrs_title'))
                for a in attrs[:8]:
                    lines.append(f"- {a.get('name')}: {a.get('raw', a.get('value', ''))}")
            else:
                lines.append(i18n.t('smart.no_attrs'))
        self.attrs_label.set_text('\n'.join(lines))
        detail = ''
        if not result.ok and result.error:
            detail = i18n.t('smart.error') + '\n' + _limit(result.error)
        elif not result.ok and not attrs and overall == 'unknown':
            detail = i18n.t('smart.error')
        self.details_label.set_text(detail)
        self.status.set_text('')
        return GLib.SOURCE_REMOVE


class XRayDialog(Gtk.Window):
    """Raio-X da máquina: resumo por tópicos e detalhes expansíveis."""

    PROGRAM_RENDER_LIMIT = 500

    def __init__(self, parent):
        super().__init__()
        self.set_title(i18n.t('xray.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(760, 620)
        self.add_css_class('dialog')
        self.add_css_class('smart-dialog')

        self._snapshot = None
        self._collecting = False
        self._priv_bios = False
        self._priv_hw = False
        self._prog_lists = {'apt': [], 'snap': [], 'flatpak_apps': []}
        self._bios_detail_text = ''
        self._hw_detail_text = ''
        self._bios_source_text = ''
        self._hw_source_text = '' 

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        hero = _vbox(0)
        hero.add_css_class('xray-hero')
        head = _hbox(12)
        head.set_margin_top(16)
        head.set_margin_bottom(16)
        head.set_margin_start(18)
        head.set_margin_end(18)
        hero_icon = _icon('🖥️')
        hero_icon.add_css_class('xray-hero-icon')
        head.append(hero_icon)
        title_box = _vbox(2)
        title_box.set_hexpand(True)
        title_box.append(_txt(i18n.t('xray.title'), 'dialog-title'))
        title_box.append(_txt(i18n.t('xray.subtitle'), 'muted', wrap=True))
        head.append(title_box)
        self.refresh_btn = Gtk.Button(label=i18n.t('xray.refresh'))
        self.refresh_btn.add_css_class('status-btn')
        self.refresh_btn.add_css_class('xray-refresh')
        self.refresh_btn.connect('clicked', lambda *_: self._collect())
        head.append(self.refresh_btn)
        hero.append(head)
        root.append(hero)

        # Resumo
        summary_card = _vbox(2)
        summary_card.add_css_class('xray-summary-card')
        summary_card.append(_txt(i18n.t('xray.summary'), 'card-title'))
        self.summary_bios = self._make_summary_row(
            summary_card, '🧩', 'xray.bios', 'blue')
        self.summary_hw = self._make_summary_row(
            summary_card, '⚙️', 'xray.hardware', 'purple')
        self.summary_prog = self._make_summary_row(
            summary_card, '📦', 'xray.programs', 'green')
        root.append(summary_card)

        self.status = _txt('', 'muted', wrap=True)
        root.append(self.status)

        # BIOS
        self.bios_details = self._make_text_area(180)
        self.bios_source = _txt('', 'xray-source')
        self.bios_full_btn = Gtk.Button(label='🔒 ' + i18n.t('xray.details_full'))
        self.bios_full_btn.add_css_class('btn-secondary')
        self.bios_full_btn.add_css_class('xray-action')
        self.bios_full_btn.connect('clicked', lambda *_: self._fetch_priv_bios())
        bios_box = _vbox(10)
        bios_box.append(self.bios_source)
        bios_box.append(self.bios_details['scroll'])
        bios_box.append(self.bios_full_btn)
        self.bios_card = self._make_card(
            '🧩', i18n.t('xray.bios'), i18n.t('xray.bios.subtitle'),
            variant='blue', on_open=self._load_bios_details)
        self.bios_card['body'].append(bios_box)
        root.append(self.bios_card['card'])

        # Hardware
        self.hw_details = self._make_text_area(220)
        self.hw_source = _txt('', 'xray-source')
        self.hw_full_btn = Gtk.Button(label='🔒 ' + i18n.t('xray.details_full'))
        self.hw_full_btn.add_css_class('btn-secondary')
        self.hw_full_btn.add_css_class('xray-action')
        self.hw_full_btn.connect('clicked', lambda *_: self._fetch_priv_hw())
        hw_box = _vbox(10)
        hw_box.append(self.hw_source)
        hw_box.append(self.hw_details['scroll'])
        hw_box.append(self.hw_full_btn)
        self.hw_card = self._make_card(
            '⚙️', i18n.t('xray.hardware'), i18n.t('xray.hardware.subtitle'),
            variant='purple', on_open=self._load_hw_details)
        self.hw_card['body'].append(hw_box)
        root.append(self.hw_card['card'])

        # Programas
        self.prog_box = _vbox(10)
        self.prog_note = _txt('', 'xray-source', wrap=True)
        self.prog_box.append(self.prog_note)
        self.prog_sections = {}
        for key, title_key, icon, variant in (
            ('apt', 'xray.programs.apt', '📦', 'blue'),
            ('snap', 'xray.programs.snap', '🟠', 'orange'),
            ('flatpak_apps', 'xray.programs.flatpak', '🫐', 'teal'),
        ):
            sec = self._make_prog_section(key, i18n.t(title_key), icon, variant)
            self.prog_sections[key] = sec
            self.prog_box.append(sec['card']['card'])
        self.prog_card = self._make_card(
            '📦', i18n.t('xray.programs'), i18n.t('xray.programs.subtitle'),
            variant='green', on_open=self._load_programs)
        self.prog_card['body'].append(self.prog_box)
        root.append(self.prog_card['card'])

        sep = Gtk.Separator()
        sep.set_margin_top(6)
        sep.set_margin_bottom(6)
        root.append(sep)

        footer = _hbox(10)
        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        footer.append(close)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        self.export_btn = Gtk.Button(label=i18n.t('xray.export_html'))
        self.export_btn.add_css_class('btn-green')
        self.export_btn.connect('clicked', lambda *_: self._export_html())
        footer.append(self.export_btn)
        root.append(footer)

        scroller.set_child(root)
        self.set_child(scroller)
        self._collect()

    def _make_text_area(self, min_height=160):
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_left_margin(8)
        view.set_right_margin(8)
        view.set_top_margin(8)
        view.set_bottom_margin(8)
        view.set_pixels_above_lines(2)
        view.set_pixels_below_lines(2)
        view.add_css_class('xray-detail')
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(min_height)
        scroll.set_child(view)
        return {'view': view, 'scroll': scroll, 'buffer': view.get_buffer()}

    def _make_chip(self, icon, variant='blue', small=False):
        chip = Gtk.Label(label=icon)
        chip.add_css_class('xray-chip')
        chip.add_css_class('xray-chip-' + variant)
        if small:
            chip.add_css_class('xray-chip-sm')
        chip.set_valign(Gtk.Align.CENTER)
        return chip

    def _make_summary_row(self, parent, icon, label_key, variant):
        row = _hbox(10)
        row.add_css_class('xray-summary-row')
        row.append(self._make_chip(icon, variant, small=True))
        text_box = _vbox(1)
        text_box.set_hexpand(True)
        text_box.append(_txt(i18n.t(label_key), 'xray-summary-label'))
        value = _txt('—', 'xray-summary-value', wrap=True)
        text_box.append(value)
        row.append(text_box)
        parent.append(row)
        return value

    def _make_card(self, icon, title, subtitle='', badge='', variant='blue',
                   compact=False, on_open=None):
        card = _vbox(0)
        card.add_css_class('xray-card')
        if compact:
            card.add_css_class('xray-subcard')

        header = Gtk.Button()
        header.set_has_frame(False)
        header.add_css_class('xray-card-header')
        row = _hbox(10)
        row.set_valign(Gtk.Align.CENTER)
        row.append(self._make_chip(icon, variant, small=compact))

        text_box = _vbox(1)
        text_box.set_hexpand(True)
        text_box.append(_txt(title, 'xray-card-title'))
        subtitle_lbl = _txt(subtitle, 'xray-card-sub', wrap=True)
        subtitle_lbl.set_visible(bool(subtitle))
        text_box.append(subtitle_lbl)
        row.append(text_box)

        badge_lbl = _txt(badge, 'xray-badge')
        badge_lbl.add_css_class('xray-badge-' + variant)
        badge_lbl.set_visible(bool(badge))
        row.append(badge_lbl)

        chevron = _txt('▸', 'xray-chevron')
        row.append(chevron)
        header.set_child(row)

        body = _vbox(10)
        body.add_css_class('xray-card-body')

        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        revealer.set_transition_duration(180)
        revealer.set_reveal_child(False)
        revealer.set_child(body)

        card.append(header)
        card.append(revealer)

        data = {
            'card': card, 'header': header, 'body': body, 'revealer': revealer,
            'chevron': chevron, 'badge': badge_lbl, 'subtitle': subtitle_lbl,
            'expanded': False, 'on_open': on_open,
        }
        header.connect('clicked', lambda *_: self._toggle_card(data))
        return data

    def _toggle_card(self, card, expand=None):
        if expand is None:
            expand = not card['expanded']
        card['expanded'] = expand
        card['revealer'].set_reveal_child(expand)
        card['chevron'].set_text('▾' if expand else '▸')
        if expand and card.get('on_open'):
            card['on_open']()

    def _set_text_area(self, area, text):
        area['buffer'].set_text(text or '')

    def _set_status(self, text):
        self.status.set_text(text or '')
        self.status.set_visible(bool(text))

    def _get_text_area(self, area):
        buf = area['buffer']
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def _make_prog_section(self, key, title, icon='📦', variant='blue'):
        card = self._make_card(
            icon, title, badge='', variant=variant, compact=True,
            on_open=lambda: self._update_prog_list(key))
        box = card['body']
        search = Gtk.SearchEntry()
        search.set_placeholder_text(i18n.t('xray.search'))
        search.add_css_class('xray-search')
        showing = _txt('', 'muted')
        area = self._make_text_area(160)
        box.append(search)
        box.append(showing)
        box.append(area['scroll'])
        search.connect('search-changed', lambda *_: self._update_prog_list(key))
        return {
            'card': card, 'box': box, 'search': search,
            'showing': showing, 'area': area,
        }

    def _set_collecting(self, busy):
        self._collecting = busy
        self.refresh_btn.set_sensitive(not busy)
        self.bios_full_btn.set_sensitive(not busy)
        self.hw_full_btn.set_sensitive(not busy)
        if busy:
            self._set_status(i18n.t('xray.collecting'))
        else:
            self._set_status('')

    def _collect(self):
        if self._collecting:
            return
        self._set_collecting(True)
        threading.Thread(target=self._collect_work, daemon=True,
                         name='cleanix-xray').start()

    def _collect_work(self):
        try:
            snap = xray.collect_unprivileged()
        except Exception as exc:
            snap = {'bios': {'summary': '', 'details': str(exc), 'fields': {}},
                    'hardware': {'summary': '', 'details': ''},
                    'programs': {'apt': [], 'snap': [], 'flatpak_apps': [],
                                 'flatpak_runtimes': 0, 'summary': ''},
                    'limitations': [str(exc)]}
        GLib.idle_add(self._apply_snapshot, snap)

    def _apply_snapshot(self, snap):
        self._snapshot = snap
        bios = snap.get('bios', {})
        hw = snap.get('hardware', {})
        prog = snap.get('programs', {})
        self.summary_bios.set_text(bios.get('summary') or i18n.t('xray.unavailable'))
        self.summary_hw.set_text(hw.get('summary') or i18n.t('xray.unavailable'))
        ps = prog.get('summary') or ''
        rt = prog.get('flatpak_runtimes', 0)
        self.summary_prog.set_text(ps or i18n.t('xray.unavailable'))
        self._prog_lists['apt'] = prog.get('apt') or []
        self._prog_lists['snap'] = prog.get('snap') or []
        self._prog_lists['flatpak_apps'] = prog.get('flatpak_apps') or []
        total_progs = sum(len(v) for v in self._prog_lists.values())
        self.prog_card['badge'].set_text(str(total_progs))
        self.prog_card['badge'].set_visible(bool(total_progs))
        # update details if not replaced by privileged
        if not self._priv_bios:
            self._bios_detail_text = bios.get('details') or i18n.t('xray.unavailable')
            self._bios_source_text = i18n.t('xray.source_unprivileged')
            self._set_text_area(self.bios_details, self._bios_detail_text)
            self.bios_source.set_text(self._bios_source_text)
        if not self._priv_hw:
            self._hw_detail_text = hw.get('details') or i18n.t('xray.unavailable')
            self._hw_source_text = i18n.t('xray.source_unprivileged')
            self._set_text_area(self.hw_details, self._hw_detail_text)
            self.hw_source.set_text(self._hw_source_text)
        self.prog_note.set_text(i18n.t('xray.programs.runtimes', n=rt))
        for key in self.prog_sections:
            self._update_prog_list(key)
        self._set_collecting(False)
        return GLib.SOURCE_REMOVE

    def _load_bios_details(self):
        if self._snapshot and not self._priv_bios:
            bios = self._snapshot.get('bios', {})
            if not self._get_text_area(self.bios_details):
                self._set_text_area(
                    self.bios_details,
                    bios.get('details') or i18n.t('xray.unavailable'))

    def _load_hw_details(self):
        if self._snapshot and not self._priv_hw:
            hw = self._snapshot.get('hardware', {})
            if not self._get_text_area(self.hw_details):
                self._set_text_area(
                    self.hw_details,
                    hw.get('details') or i18n.t('xray.unavailable'))

    def _load_programs(self):
        for key in self.prog_sections:
            self._update_prog_list(key)

    def _fetch_priv_bios(self):
        if self._collecting:
            return
        self.bios_full_btn.set_sensitive(False)
        self._set_status(i18n.t('xray.collecting'))
        threading.Thread(target=self._priv_bios_work, daemon=True,
                         name='cleanix-xray-bios').start()

    def _priv_bios_work(self):
        try:
            res = xray.collect_privileged_bios()
        except Exception as exc:
            res = {'ok': False, 'details': '', 'source': 'dmidecode', 'error': str(exc)}
        GLib.idle_add(self._apply_priv_bios, res)

    def _apply_priv_bios(self, res):
        self.bios_full_btn.set_sensitive(True)
        self._set_status('')
        if res.get('ok'):
            self._priv_bios = True
            self._bios_detail_text = res.get('details') or i18n.t('xray.unavailable')
            self._bios_source_text = i18n.t('xray.source_privileged')
            self._set_text_area(self.bios_details, self._bios_detail_text)
            self.bios_source.set_text(self._bios_source_text)
        else:
            err = res.get('error') or i18n.t('xray.unavailable')
            self.bios_source.set_text(i18n.t('xray.source_unprivileged'))
            # keep unprivileged details, show error in status
            self._set_status(err)
        return GLib.SOURCE_REMOVE

    def _fetch_priv_hw(self):
        if self._collecting:
            return
        self.hw_full_btn.set_sensitive(False)
        self._set_status(i18n.t('xray.collecting'))
        threading.Thread(target=self._priv_hw_work, daemon=True,
                         name='cleanix-xray-hw').start()

    def _priv_hw_work(self):
        try:
            res = xray.collect_privileged_hardware()
        except Exception as exc:
            res = {'ok': False, 'details': '', 'source': 'lshw', 'error': str(exc)}
        GLib.idle_add(self._apply_priv_hw, res)

    def _apply_priv_hw(self, res):
        self.hw_full_btn.set_sensitive(True)
        self._set_status('')
        if res.get('ok'):
            self._priv_hw = True
            self._hw_detail_text = res.get('details') or i18n.t('xray.unavailable')
            self._hw_source_text = i18n.t('xray.source_privileged')
            self._set_text_area(self.hw_details, self._hw_detail_text)
            self.hw_source.set_text(self._hw_source_text)
        else:
            err = res.get('error') or i18n.t('xray.unavailable')
            self.hw_source.set_text(i18n.t('xray.source_unprivileged'))
            self._set_status(err)
        return GLib.SOURCE_REMOVE

    def _update_prog_list(self, key):
        sec = self.prog_sections.get(key)
        if not sec:
            return
        items = self._prog_lists.get(key) or []
        q = (sec['search'].get_text() or '').strip().lower()
        if q:
            filtered = [item for item in items
                        if q in item[0].lower()
                        or q in (item[1] if len(item) > 1 else '').lower()]
        else:
            filtered = list(items)
        badge = sec['card']['badge']
        badge.set_text(str(len(items)))
        badge.set_visible(bool(items))
        total = len(filtered)
        show = filtered[: self.PROGRAM_RENDER_LIMIT]
        if show:
            lines = []
            for item in show:
                name = item[0]
                version = item[1] if len(item) > 1 else ''
                size = item[2] if len(item) > 2 else ''
                parts = [name]
                if version:
                    parts.extend(['—', version])
                if size:
                    parts.extend(['·', size])
                lines.append(' '.join(parts))
            self._set_text_area(sec['area'], '\n'.join(lines))
        else:
            self._set_text_area(sec['area'], i18n.t('xray.empty'))
        sec['showing'].set_text(
            i18n.t('xray.showing', n=len(show), m=total))


    def _export_html(self):
        dialog = Gtk.FileDialog()
        dialog.set_title(i18n.t('xray.export_title'))
        dialog.set_initial_name(i18n.t('xray.export_filename'))
        try:
            dialog.save(self, None, self._on_export_response)
        except Exception:
            # fallback: save to home
            self._write_export(Path.home() / i18n.t('xray.export_filename'))

    def _on_export_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
        except Exception:
            return
        if file is None:
            return
        path = file.get_path()
        if not path:
            return
        self._write_export(Path(path))

    def _write_export(self, path):
        if self._priv_bios and self._priv_hw:
            self._finish_export(path, None)
            return
        self.export_btn.set_sensitive(False)
        self._set_status(i18n.t('xray.collecting_full'))
        threading.Thread(target=self._export_work, args=(path,), daemon=True,
                         name='cleanix-xray-export').start()

    def _export_work(self, path):
        try:
            res = xray.collect_privileged_all()
        except Exception as exc:
            res = {'ok': False, 'bios': {}, 'hardware': {}, 'error': str(exc)}
        GLib.idle_add(self._finish_export, path, res)

    def _finish_export(self, path, res):
        self.export_btn.set_sensitive(True)
        self._set_status('')
        priv_error = ''
        if res is not None:
            bios = res.get('bios') or {}
            hw = res.get('hardware') or {}
            if bios.get('ok') and bios.get('details'):
                self._priv_bios = True
                self._bios_detail_text = bios['details']
                self._bios_source_text = i18n.t('xray.source_privileged')
                self._set_text_area(self.bios_details, self._bios_detail_text)
                self.bios_source.set_text(self._bios_source_text)
            if hw.get('ok') and hw.get('details'):
                self._priv_hw = True
                self._hw_detail_text = hw['details']
                self._hw_source_text = i18n.t('xray.source_privileged')
                self._set_text_area(self.hw_details, self._hw_detail_text)
                self.hw_source.set_text(self._hw_source_text)
            if not res.get('ok'):
                priv_error = res.get('error') or ''
        try:
            html = self._build_export_html(priv_error)
            Path(path).write_text(html, encoding='utf-8')
            opened = self._open_report(path)
            body = i18n.t('xray.export_done_body', path=str(path))
            if opened:
                body += '\n\n' + i18n.t('xray.export_opened')
            if priv_error:
                body += '\n\n' + i18n.t(
                    'xray.html.priv_missing_body', detail=priv_error)
            show_info(self, i18n.t('xray.export_done_title'), body)
        except Exception as exc:
            show_info(self, i18n.t('xray.export_error_title'),
                      i18n.t('xray.export_error_body', detail=str(exc)))
        return GLib.SOURCE_REMOVE

    def _open_report(self, path):
        try:
            uri = Gio.File.new_for_path(str(path)).get_uri()
            return bool(Gio.AppInfo.launch_default_for_uri(uri, None))
        except Exception as exc:
            log.warning('Não foi possível abrir o relatório %s: %s', path, exc)
            return False

    def _build_export_html(self, priv_error=''):
        snap = self._snapshot or {}
        bios = snap.get('bios', {}) or {}
        hw = snap.get('hardware', {}) or {}
        return xray.build_report_html(
            snap,
            bios_details=self._bios_detail_text or bios.get('details') or '',
            hw_details=self._hw_detail_text or hw.get('details') or '',
            bios_source=self._bios_source_text,
            hw_source=self._hw_source_text,
            priv_error=priv_error,
        )
