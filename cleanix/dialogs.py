import os
#!/usr/bin/env python3
"""Diálogos do Cleanix: avisos, confirmação, detalhes e histórico."""

import logging
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from . import (adjustments, autostart, history, i18n, memory, optimizer, settings,
               smart_history, snapshots, space, systeminfo, xray)
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
        self.set_default_size(720, -1)
        self.add_css_class('dialog')

        root = _vbox(12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(heading, 'dialog-title'))
        if self.subtitle_key:
            root.append(_txt(i18n.t(self.subtitle_key), 'muted', wrap=True))

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(2)
        flow.set_min_children_per_line(1)
        flow.set_column_spacing(12)
        flow.set_row_spacing(12)
        flow.set_homogeneous(True)
        flow.set_valign(Gtk.Align.START)

        for action in self.actions:
            flow.insert(self._action_card(action), -1)
        root.append(flow)

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

    def _action_card(self, action):
        card = _vbox(8)
        card.add_css_class('card')
        card.set_hexpand(True)

        title = _txt(i18n.t(action['label_key']), 'cat-name', wrap=True)
        card.append(title)

        description = _txt(i18n.t(action['description_key']), 'muted', wrap=True)
        description.set_vexpand(True)
        card.append(description)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        card.append(spacer)

        button = Gtk.Button(label=i18n.t(action['label_key']))
        button.add_css_class('btn-secondary')
        button.set_halign(Gtk.Align.FILL)
        button.set_hexpand(True)
        if action.get('dialog') is not None:
            button.connect('clicked', lambda *_: action['dialog'](self))
        else:
            button.connect('clicked', self._on_clicked, action)
        card.append(button)
        self._buttons[action['label_key']] = button
        return card

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
        self.status.set_visible(True)
        self.status.set_text(i18n.t('action.status.running', label=label))

        def work():
            result = execute_command(action['command'], action['as_root'])
            GLib.idle_add(self._done, button, action, result)

        threading.Thread(target=work, daemon=True, name='cleanix-action').start()

    def _done(self, button, action, result):
        label = i18n.t(action['label_key'])
        button.set_label(label)
        button.set_sensitive(True)

        self.status.set_visible(True)
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



class _PreviewCleanupDialog(Gtk.Window):
    title_key = ''
    subtitle_key = ''
    unavailable_key = ''

    def __init__(self, parent):
        super().__init__()
        self.set_title(i18n.t(self.title_key))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(560, 420)
        self.add_css_class('dialog')

        self._items = []
        self._data = {}

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(i18n.t(self.title_key), 'dialog-title'))
        if self.subtitle_key:
            root.append(_txt(i18n.t(self.subtitle_key), 'muted', wrap=True))

        self.status = _txt(i18n.t('common.loading') if hasattr(i18n, 't') else '...', 'muted', wrap=True)
        root.append(self.status)

        self.summary_label = _txt('', 'cat-name', wrap=True)
        self.summary_label.set_visible(False)
        root.append(self.summary_label)

        self.area = self._make_text_area(180)
        root.append(self.area['scroll'])

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

        self.refresh_btn = Gtk.Button(label=i18n.t('optimizer.preview.refresh'))
        self.refresh_btn.add_css_class('btn-secondary')
        self.refresh_btn.connect('clicked', lambda *_: self._scan())
        footer.append(self.refresh_btn)

        self.remove_btn = Gtk.Button(label=i18n.t('optimizer.preview.remove'))
        self.remove_btn.add_css_class('btn-green')
        self.remove_btn.set_sensitive(False)
        self.remove_btn.connect('clicked', lambda *_: self._confirm_remove())
        footer.append(self.remove_btn)

        root.append(footer)
        self.set_child(root)
        self._scan()

    def _make_text_area(self, min_height=160):
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_left_margin(8)
        view.set_right_margin(8)
        view.set_top_margin(8)
        view.set_bottom_margin(8)
        view.add_css_class('xray-detail')
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(min_height)
        scroll.set_child(view)
        return {'view': view, 'scroll': scroll, 'buffer': view.get_buffer()}

    def _set_text(self, text):
        self.area['buffer'].set_text(text or '')

    def _scan(self):
        self.refresh_btn.set_sensitive(False)
        self.remove_btn.set_sensitive(False)
        self.summary_label.set_visible(False)
        self.status.set_text(self.scanning_text())
        self._set_text('')
        threading.Thread(target=self._scan_work, daemon=True).start()

    def scanning_text(self):
        return i18n.t('xray.collecting')

    def _scan_work(self):
        try:
            data = self.preview()
        except Exception as exc:
            data = {'available': True, 'items': [], 'empty': True, 'error': str(exc), 'output': ''}
        GLib.idle_add(self._apply_preview, data)

    def preview(self):
        return {'available': True, 'items': [], 'empty': True, 'error': '', 'output': ''}

    def format_items(self, data):
        return ''

    def can_remove(self, data):
        items = data.get('items') or []
        return bool(items) and not data.get('unparsed')

    def _apply_preview(self, data):
        self._data = data or {}
        self._items = list(self._data.get('items') or [])
        self.refresh_btn.set_sensitive(True)
        if not self._data.get('available', True):
            self.status.set_text(i18n.t(self.unavailable_key))
            self._set_text(self._data.get('error') or '')
            self.remove_btn.set_sensitive(False)
            return GLib.SOURCE_REMOVE
        if self._data.get('unparsed'):
            self.status.set_text(i18n.t('optimizer.flatpakunused.unparsed'))
            self._set_text(self._data.get('output') or '')
            self.summary_label.set_text('')
            self.summary_label.set_visible(False)
            self.remove_btn.set_sensitive(False)
            return GLib.SOURCE_REMOVE
        empty = self._data.get('empty', not self._items)
        if empty:
            self.status.set_text(self.empty_text())
            self._set_text('')
            self.summary_label.set_visible(False)
            self.remove_btn.set_sensitive(False)
        else:
            self.status.set_text(i18n.t('optimizer.preview.items', count=len(self._items)))
            extra = self._data.get('freed_text') or ''
            if extra:
                self.summary_label.set_text(i18n.t('optimizer.autoremove.freed', value=extra) if self._data.get('kind') == 'apt' else extra)
                self.summary_label.set_visible(True)
            else:
                self.summary_label.set_visible(False)
            self._set_text(self.format_items(self._data))
            self.remove_btn.set_sensitive(self.can_remove(self._data))
        return GLib.SOURCE_REMOVE

    def empty_text(self):
        return i18n.t('xray.empty')

    def _confirm_remove(self):
        if not self.can_remove(self._data):
            return
        confirm(self, self.confirm_title(), self.confirm_body(),
                self.confirm_action(), self._do_remove)

    def confirm_title(self):
        return i18n.t('action.confirm.title', label=self.get_title())

    def confirm_body(self):
        return ''

    def confirm_action(self):
        return i18n.t('optimizer.preview.remove')

    def _do_remove(self):
        self.remove_btn.set_sensitive(False)
        self.refresh_btn.set_sensitive(False)
        self.status.set_text(self.running_text())
        threading.Thread(target=self._remove_work, daemon=True).start()

    def running_text(self):
        return i18n.t('action.running')

    def _remove_work(self):
        try:
            ok, message = self.remove(self._data)
        except Exception as exc:
            ok, message = False, str(exc)
        GLib.idle_add(self._after_remove, ok, message)

    def remove(self, data):
        return False, ''

    def _after_remove(self, ok, message):
        self.refresh_btn.set_sensitive(True)
        if ok:
            show_info(self, self.get_title(), message or i18n.t('action.done.body'))
        else:
            show_info(self, self.get_title(), message or i18n.t('action.failed.body'))
        self._scan()
        return GLib.SOURCE_REMOVE


class AptAutoremoveDialog(_PreviewCleanupDialog):
    title_key = 'optimizer.autoremove.title'
    subtitle_key = 'optimizer.autoremove.subtitle'
    unavailable_key = 'optimizer.autoremove.unavailable'

    def scanning_text(self):
        return i18n.t('optimizer.autoremove.scanning')

    def empty_text(self):
        return i18n.t('optimizer.autoremove.none')

    def preview(self):
        data = optimizer.preview_apt_autoremove()
        data['kind'] = 'apt'
        return data

    def format_items(self, data):
        return '\n'.join('• ' + name for name in (data.get('items') or []))

    def confirm_title(self):
        return i18n.t('optimizer.autoremove.confirm_title')

    def confirm_body(self):
        items = data = self._data.get('items') or []
        names = '\n'.join('• ' + n for n in items[:20])
        if len(items) > 20:
            names += '\n… +' + str(len(items) - 20)
        return i18n.t('optimizer.autoremove.confirm_body', count=len(items), names=names)

    def confirm_action(self):
        return i18n.t('optimizer.autoremove.confirm_action')

    def running_text(self):
        return i18n.t('optimizer.autoremove.running')

    def remove(self, data):
        result = execute_command('apt-get autoremove -y', as_root=True, timeout=600)
        if result.ok:
            return True, i18n.t('optimizer.autoremove.done')
        return False, result.error or i18n.t('optimizer.autoremove.failed')


class SnapCleanupDialog(_PreviewCleanupDialog):
    title_key = 'optimizer.snapclean.title'
    subtitle_key = 'optimizer.snapclean.subtitle'
    unavailable_key = 'optimizer.snapclean.unavailable'

    def scanning_text(self):
        return i18n.t('optimizer.snapclean.scanning')

    def empty_text(self):
        return i18n.t('optimizer.snapclean.none')

    def preview(self):
        return optimizer.preview_snap_disabled()

    def format_items(self, data):
        lines = []
        for item in data.get('items') or []:
            lines.append(f"• {item.get('name')}  {item.get('version','')}  (rev {item.get('rev','')})")
        return '\n'.join(lines)

    def confirm_title(self):
        return i18n.t('optimizer.snapclean.confirm_title')

    def confirm_body(self):
        return i18n.t('optimizer.snapclean.confirm_body', count=len(self._items))

    def confirm_action(self):
        return i18n.t('optimizer.snapclean.confirm_action')

    def running_text(self):
        return i18n.t('optimizer.snapclean.running')

    def remove(self, data):
        errors = []
        removed = 0
        for item in data.get('items') or []:
            name = item.get('name')
            rev = item.get('rev')
            if not name or not rev:
                continue
            cmd = f"snap remove {name} --revision={rev}"
            result = execute_command(cmd, as_root=True, timeout=300)
            if result.ok:
                removed += 1
            else:
                errors.append(f"{name} rev {rev}: {result.error or 'erro'}")
        if errors and removed:
            return True, i18n.t('optimizer.snapclean.partial') + '\n' + '\n'.join(errors[:10])
        if errors:
            return False, '\n'.join(errors[:10])
        return True, i18n.t('optimizer.snapclean.done')


class FlatpakUnusedDialog(_PreviewCleanupDialog):
    title_key = 'optimizer.flatpakunused.title'
    subtitle_key = 'optimizer.flatpakunused.subtitle'
    unavailable_key = 'optimizer.flatpakunused.unavailable'

    def scanning_text(self):
        return i18n.t('optimizer.flatpakunused.scanning')

    def empty_text(self):
        return i18n.t('optimizer.flatpakunused.none')

    def preview(self):
        return optimizer.preview_flatpak_unused()

    def format_items(self, data):
        items = data.get('items') or []
        if items:
            return '\n'.join('• ' + str(i) for i in items)
        return data.get('output') or ''

    def can_remove(self, data):
        # allow remove if we have items, or if unparsed but user saw output? spec says "exige confirmação antes de qualquer remoção" when unparsed - but safer to only allow when we have items
        return bool(data.get('items'))

    def confirm_title(self):
        return i18n.t('optimizer.flatpakunused.confirm_title')

    def confirm_body(self):
        return i18n.t('optimizer.flatpakunused.confirm_body')

    def confirm_action(self):
        return i18n.t('optimizer.flatpakunused.confirm_action')

    def running_text(self):
        return i18n.t('optimizer.flatpakunused.running')

    def remove(self, data):
        result = execute_command('flatpak uninstall --unused -y', as_root=False, timeout=600)
        if result.ok:
            return True, i18n.t('optimizer.flatpakunused.done')
        return False, result.error or i18n.t('optimizer.flatpakunused.failed')


OPTIMIZER_ACTIONS = (
    {
        'label_key': 'optimizer.autoremove.title',
        'description_key': 'optimizer.autoremove.desc',
        'dialog': lambda parent: AptAutoremoveDialog(parent).present(),
    },
    {
        'label_key': 'optimizer.clean.label',
        'description_key': 'optimizer.clean.desc',
        'detail_key': 'optimizer.clean.detail',
        'command': 'apt-get clean',
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
    {
        'label_key': 'optimizer.snapclean.title',
        'description_key': 'optimizer.snapclean.desc',
        'dialog': lambda parent: SnapCleanupDialog(parent).present(),
    },
    {
        'label_key': 'optimizer.flatpakunused.title',
        'description_key': 'optimizer.flatpakunused.desc',
        'dialog': lambda parent: FlatpakUnusedDialog(parent).present(),
    },
)


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

        self._reminder_switch = Gtk.Switch()
        self._reminder_switch.set_active(self._settings.reminder_enabled)
        self._reminder_switch.set_valign(Gtk.Align.CENTER)
        self._reminder_switch.connect('notify::active', self._on_toggle)
        root.append(self._row(
            i18n.t('settings.reminder.enable'),
            i18n.t('settings.reminder.enable_desc'), self._reminder_switch))

        self._reminder_intervals = [7, 14, 30]
        labels = [i18n.t('settings.reminder.weekly'),
                  i18n.t('settings.reminder.biweekly'),
                  i18n.t('settings.reminder.monthly')]
        self._reminder_dropdown = Gtk.DropDown.new_from_strings(labels)
        try:
            idx = self._reminder_intervals.index(self._settings.reminder_interval_days)
        except ValueError:
            idx = 0
        self._reminder_dropdown.set_selected(idx)
        self._reminder_dropdown.set_valign(Gtk.Align.CENTER)
        self._reminder_dropdown.connect('notify::selected', self._on_toggle)
        root.append(self._row(
            i18n.t('settings.reminder.interval'),
            i18n.t('settings.reminder.desc'), self._reminder_dropdown))

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

    def _current_settings(self):
        idx = self._reminder_dropdown.get_selected()
        if idx < 0 or idx >= len(self._reminder_intervals):
            idx = 0
        return settings.Settings(
            confirm_before_clean=self._confirm_switch.get_active(),
            keep_history=self._history_switch.get_active(),
            language=self._settings.language,
            reminder_enabled=self._reminder_switch.get_active(),
            reminder_interval_days=self._reminder_intervals[idx],
        )

    def _on_toggle(self, _switch, _pspec):
        if self._recording:
            return
        self._settings = self._current_settings()
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
            reminder_enabled=self._reminder_switch.get_active(),
            reminder_interval_days=self._reminder_intervals[
                max(0, min(self._reminder_dropdown.get_selected(), len(self._reminder_intervals)-1))],
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
        important = [a for a in attrs if a.get('critical')]
        lines = []
        if important:
            lines.append(i18n.t('smart.attrs_title'))
            for a in important:
                lines.append(f"- {a.get('name')}: {a.get('raw', a.get('value', ''))}")
        else:
            if attrs:
                lines.append(i18n.t('smart.attrs_title'))
                for a in attrs[:8]:
                    lines.append(f"- {a.get('name')}: {a.get('raw', a.get('value', ''))}")
            else:
                lines.append(i18n.t('smart.no_attrs'))

        comparison = None
        try:
            comparison = smart_history.compare_previous(
                self.disk_name, self.disk_model, parsed)
            smart_history.record_check(
                self.disk_name, self.disk_model, parsed)
        except Exception as exc:
            log.warning('Falha no histórico SMART: %s', exc)

        if comparison and comparison.get('worsened'):
            lines.append('')
            lines.append('⚠ ' + i18n.t('smart.degraded'))
            for msg in comparison.get('messages') or []:
                lines.append('  - ' + str(msg))

        self.attrs_label.set_text('\n'.join(lines))
        detail = ''
        if not result.ok and result.error:
            detail = i18n.t('smart.error') + '\n' + _limit(result.error)
        elif not result.ok and not attrs and overall == 'unknown':
            detail = i18n.t('smart.error')
        self.details_label.set_text(detail)
        self.status.set_text('')
        return GLib.SOURCE_REMOVE



class CompareSnapshotsDialog(Gtk.Window):
    def __init__(self, parent, current_provider=None):
        super().__init__()
        self.set_title(i18n.t('xray.compare.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(720, 520)
        self.add_css_class('dialog')
        self._current_provider = current_provider
        self._items = snapshots.list_snapshots()

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)
        root.append(_txt(i18n.t('xray.compare.title'), 'dialog-title'))
        root.append(_txt(i18n.t('xray.compare.subtitle'), 'muted', wrap=True))

        controls = _hbox(10)
        controls.set_homogeneous(True)

        base_box = _vbox(4)
        base_box.append(_txt(i18n.t('xray.compare.base'), 'cat-name'))
        self.base_combo = Gtk.ComboBoxText()
        base_box.append(self.base_combo)
        controls.append(base_box)

        target_box = _vbox(4)
        target_box.append(_txt(i18n.t('xray.compare.target'), 'cat-name'))
        self.target_combo = Gtk.ComboBoxText()
        target_box.append(self.target_combo)
        controls.append(target_box)
        root.append(controls)

        self._populate_combos()

        run_btn = Gtk.Button(label=i18n.t('xray.compare.run'))
        run_btn.add_css_class('btn-green')
        run_btn.connect('clicked', lambda *_: self._run_compare())
        root.append(run_btn)

        self.area = Gtk.TextView()
        self.area.set_editable(False)
        self.area.set_cursor_visible(False)
        self.area.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.area.set_left_margin(8)
        self.area.set_right_margin(8)
        self.area.set_top_margin(8)
        self.area.set_bottom_margin(8)
        self.area.add_css_class('xray-detail')
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(280)
        scroll.set_child(self.area)
        root.append(scroll)

        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        root.append(close)

        self.set_child(root)
        if self._items:
            self._run_compare()
        else:
            self._set_text(i18n.t('xray.compare.none'))

    def _populate_combos(self):
        def label_for(item):
            g = item.get('generated') or ''
            prod = item.get('product') or item.get('os') or ''
            return (g + (' — ' + prod if prod else '')).strip() or item.get('path', '')
        self._choices = [('__current__', i18n.t('xray.compare.current'))]
        for item in self._items:
            self._choices.append((item['path'], label_for(item)))
        for combo in (self.base_combo, self.target_combo):
            combo.remove_all()
            for _, label in self._choices:
                combo.append_text(label)
        if len(self._choices) > 1:
            self.base_combo.set_active(1)
            self.target_combo.set_active(0)
        else:
            self.base_combo.set_active(0)
            self.target_combo.set_active(0)

    def _set_text(self, text):
        self.area.get_buffer().set_text(text or '')

    def _get_data(self, idx):
        if idx < 0 or idx >= len(self._choices):
            return None
        key = self._choices[idx][0]
        if key == '__current__':
            if self._current_provider:
                try:
                    return self._current_provider()
                except Exception:
                    return None
            return None
        try:
            return snapshots.load_snapshot(key)
        except Exception:
            return None

    def _run_compare(self):
        if not self._items and self._choices and len(self._choices) <= 1:
            self._set_text(i18n.t('xray.compare.no_saved'))
            return
        base = self._get_data(self.base_combo.get_active())
        target = self._get_data(self.target_combo.get_active())
        if base is None or target is None:
            self._set_text(i18n.t('xray.unavailable'))
            return
        diff = snapshots.compare_snapshots(base, target)
        self._set_text(self._format_diff(diff))

    def _format_diff(self, diff):
        lines = []
        # programs
        p = diff.get('programs') or {}
        prog_lines = []
        for origin in ('apt', 'snap', 'flatpak_apps'):
            added = (p.get('added') or {}).get(origin) or []
            removed = (p.get('removed') or {}).get(origin) or []
            changed = (p.get('changed') or {}).get(origin) or []
            if added:
                prog_lines.append(f"  [{origin}] {i18n.t('xray.compare.added')}: " + ', '.join(added[:20]) + ('…' if len(added) > 20 else ''))
            if removed:
                prog_lines.append(f"  [{origin}] {i18n.t('xray.compare.removed')}: " + ', '.join(removed[:20]) + ('…' if len(removed) > 20 else ''))
            if changed:
                names = [f"{c['name']} ({c.get('old','')} → {c.get('new','')})" for c in changed[:20]]
                prog_lines.append(f"  [{origin}] {i18n.t('xray.compare.changed')}: " + ', '.join(names) + ('…' if len(changed) > 20 else ''))
        if prog_lines:
            lines.append('[' + i18n.t('xray.compare.programs') + ']')
            lines.extend(prog_lines)
        # disks
        disks = diff.get('disks') or []
        if disks:
            lines.append('')
            lines.append('[' + i18n.t('xray.compare.disks') + ']')
            for d in disks:
                name = (d.get('name') or '') + (' ' + d.get('mount') if d.get('mount') else '')
                lines.append(f"  • {name}: {d.get('old_pct','?')}% → {d.get('new_pct','?')}%")
        # system
        sysc = (diff.get('system') or {}).get('updates') or {}
        if sysc.get('old') != sysc.get('new') and not (sysc.get('old') is None and sysc.get('new') is None):
            lines.append('')
            lines.append('[' + i18n.t('xray.compare.system') + ']')
            lines.append(f"  • {i18n.t('xray.compare.updates')}: {sysc.get('old')} → {sysc.get('new')}")
        # bios/hardware
        if (diff.get('bios') or {}).get('changed'):
            lines.append('')
            lines.append('• ' + i18n.t('xray.compare.bios_changed'))
        if (diff.get('hardware') or {}).get('changed'):
            lines.append('• ' + i18n.t('xray.compare.hardware_changed'))
        # alerts
        alerts = diff.get('alerts') or {}
        if alerts.get('new') or alerts.get('resolved'):
            lines.append('')
            lines.append('[' + i18n.t('xray.compare.alerts') + ']')
            if alerts.get('new'):
                for a in alerts['new']:
                    lines.append(f"  + {a}")
            if alerts.get('resolved'):
                for a in alerts['resolved']:
                    lines.append(f"  - {a}")
        if not lines:
            return i18n.t('xray.compare.no_changes')
        return '\n'.join(lines)


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
        self._network_detail_text = ''
        self._system_detail_text = ''
        self._bios_source_text = ''
        self._hw_source_text = ''
        self._alert_texts = []

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
        self.updated = _txt('', 'xray-updated')
        self.updated.set_visible(False)
        title_box.append(self.updated)
        head.append(title_box)
        self.spinner = Gtk.Spinner()
        self.spinner.add_css_class('xray-spinner')
        head.append(self.spinner)
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
        self.alerts_line = _txt('', 'xray-alert-line', wrap=True)
        self.alerts_line.set_visible(False)
        summary_card.append(self.alerts_line)
        root.append(summary_card)

        actions = _hbox(8)
        actions.add_css_class('xray-toolbar')
        self.expand_btn = Gtk.Button(label=i18n.t('xray.expand_all'))
        self.expand_btn.add_css_class('btn-secondary')
        self.expand_btn.add_css_class('xray-action')
        self.expand_btn.connect('clicked', lambda *_: self._expand_all(True))
        actions.append(self.expand_btn)
        self.collapse_btn = Gtk.Button(label=i18n.t('xray.collapse_all'))
        self.collapse_btn.add_css_class('btn-secondary')
        self.collapse_btn.add_css_class('xray-action')
        self.collapse_btn.connect('clicked', lambda *_: self._expand_all(False))
        actions.append(self.collapse_btn)
        self.copy_summary_btn = Gtk.Button(label=i18n.t('xray.copy_summary'))
        self.copy_summary_btn.add_css_class('btn-secondary')
        self.copy_summary_btn.add_css_class('xray-action')
        self.copy_summary_btn.connect('clicked', lambda *_: self._copy_support_summary())
        actions.append(self.copy_summary_btn)
        self.save_snapshot_btn = Gtk.Button(label=i18n.t('xray.snapshot.save'))
        self.save_snapshot_btn.add_css_class('btn-secondary')
        self.save_snapshot_btn.add_css_class('xray-action')
        self.save_snapshot_btn.connect('clicked', lambda *_: self._save_snapshot())
        actions.append(self.save_snapshot_btn)
        self.compare_btn = Gtk.Button(label=i18n.t('xray.snapshot.compare'))
        self.compare_btn.add_css_class('btn-secondary')
        self.compare_btn.add_css_class('xray-action')
        self.compare_btn.connect('clicked', lambda *_: self._open_compare())
        actions.append(self.compare_btn)
        root.append(actions)

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
        bios_actions = _hbox(8)
        bios_actions.append(self._make_copy_button(
            lambda: self._bios_detail_text))
        bios_actions.append(self.bios_full_btn)
        bios_box.append(bios_actions)
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
        hw_actions = _hbox(8)
        hw_actions.append(self._make_copy_button(
            lambda: self._hw_detail_text))
        hw_actions.append(self.hw_full_btn)
        hw_box.append(hw_actions)
        self.hw_card = self._make_card(
            '⚙️', i18n.t('xray.hardware'), i18n.t('xray.hardware.subtitle'),
            variant='purple', on_open=self._load_hw_details)
        self.hw_card['body'].append(hw_box)
        root.append(self.hw_card['card'])

        # Rede
        self.network_details = self._make_text_area(160)
        network_box = _vbox(10)
        network_box.append(self.network_details['scroll'])
        network_box.append(self._make_copy_button(
            lambda: self._network_detail_text))
        self.network_card = self._make_card(
            '🌐', i18n.t('xray.section.network'),
            i18n.t('xray.network.subtitle'), variant='teal',
            on_open=self._load_network_details)
        self.network_card['body'].append(network_box)
        root.append(self.network_card['card'])

        # Sistema
        self.system_details = self._make_text_area(160)
        system_box = _vbox(10)
        system_box.append(self.system_details['scroll'])
        system_box.append(self._make_copy_button(
            lambda: self._system_detail_text))
        self.system_card = self._make_card(
            '🩺', i18n.t('xray.section.systeminfo'),
            i18n.t('xray.system.subtitle'), variant='blue',
            on_open=self._load_system_details)
        self.system_card['body'].append(system_box)
        root.append(self.system_card['card'])

        # Programas
        self.prog_box = _vbox(10)
        self.prog_note = _txt('', 'xray-source', wrap=True)
        self.prog_box.append(self.prog_note)
        self.global_search = Gtk.SearchEntry()
        self.global_search.set_placeholder_text(i18n.t('xray.search_all'))
        self.global_search.add_css_class('xray-search')
        self.global_search.connect(
            'search-changed', lambda *_: self._update_all_prog_lists())
        self.prog_box.append(self.global_search)
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

        self.footer_refresh_btn = Gtk.Button(label=i18n.t('xray.refresh'))
        self.footer_refresh_btn.add_css_class('btn-secondary')
        self.footer_refresh_btn.connect('clicked', lambda *_: self._collect())
        footer.append(self.footer_refresh_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        self.redact_check = Gtk.CheckButton(
            label='🔒 ' + i18n.t('xray.privacy_check'))
        self.redact_check.set_active(True)
        self.redact_check.set_tooltip_text(i18n.t('xray.privacy_check_tip'))
        self.redact_check.add_css_class('xray-privacy')
        footer.append(self.redact_check)

        self.export_json_btn = Gtk.Button(label=i18n.t('xray.export_json'))
        self.export_json_btn.add_css_class('btn-secondary')
        self.export_json_btn.connect('clicked', lambda *_: self._export('json'))
        footer.append(self.export_json_btn)

        self.export_csv_btn = Gtk.Button(label=i18n.t('xray.export_csv'))
        self.export_csv_btn.add_css_class('btn-secondary')
        self.export_csv_btn.connect('clicked', lambda *_: self._export('csv'))
        footer.append(self.export_csv_btn)

        self.export_btn = Gtk.Button(label=i18n.t('xray.export_html'))
        self.export_btn.add_css_class('btn-green')
        self.export_btn.connect('clicked', lambda *_: self._export('html'))
        footer.append(self.export_btn)
        root.append(footer)

        scroller.set_child(root)
        self.set_child(scroller)

        key = Gtk.EventControllerKey()
        key.connect('key-pressed', self._on_key)
        self.add_controller(key)

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

    def _make_copy_button(self, getter):
        btn = Gtk.Button(label='📋 ' + i18n.t('xray.copy'))
        btn.add_css_class('btn-secondary')
        btn.add_css_class('xray-action')
        btn.connect('clicked', lambda *_: self._copy_text(getter()))
        return btn

    def _copy_text(self, text):
        text = (text or '').strip()
        if not text:
            return
        try:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self._set_status(i18n.t('xray.copied'))
        except Exception as exc:
            log.warning('Falha ao copiar texto: %s', exc)
            self._set_status(i18n.t('xray.unavailable'))

    def _on_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _expand_all(self, expand):
        cards = [self.bios_card, self.hw_card, self.network_card,
                 self.system_card, self.prog_card]
        cards.extend(sec['card'] for sec in self.prog_sections.values())
        for card in cards:
            self._toggle_card(card, expand)

    def _load_network_details(self):
        if self._snapshot and not self._get_text_area(self.network_details):
            self._set_text_area(
                self.network_details,
                self._network_detail_text or i18n.t('xray.unavailable'))

    def _load_system_details(self):
        if self._snapshot and not self._get_text_area(self.system_details):
            self._set_text_area(
                self.system_details,
                self._system_detail_text or i18n.t('xray.unavailable'))

    def _copy_support_summary(self):
        snap = self._snapshot or {}
        bios = snap.get('bios', {}) or {}
        hw = snap.get('hardware', {}) or {}
        text = xray.build_support_summary(
            snap,
            bios_details=self._bios_detail_text or bios.get('details') or '',
            hw_details=self._hw_detail_text or hw.get('details') or '',
            bios_source=self._bios_source_text,
            hw_source=self._hw_source_text,
            redact=self.redact_check.get_active(),
        )
        try:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self._set_status(i18n.t('xray.summary_copied'))
        except Exception as exc:
            log.warning('Falha ao copiar resumo: %s', exc)
            self._set_status(i18n.t('xray.unavailable'))

    def _make_prog_section(self, key, title, icon='📦', variant='blue'):
        card = self._make_card(
            icon, title, badge='', variant=variant, compact=True,
            on_open=lambda: self._update_prog_list(key))
        box = card['body']
        search = Gtk.SearchEntry()
        search.set_placeholder_text(i18n.t('xray.search'))
        search.add_css_class('xray-search')
        showing = _txt('', 'muted')
        more = Gtk.Button(label=i18n.t('xray.show_all'))
        more.add_css_class('btn-secondary')
        more.add_css_class('xray-action')
        more.set_visible(False)
        more.connect('clicked', lambda *_: self._show_all_programs(key))
        area = self._make_text_area(160)
        box.append(search)
        box.append(showing)
        box.append(more)
        box.append(area['scroll'])
        search.connect('search-changed', lambda *_: self._update_prog_list(key))
        return {
            'card': card, 'box': box, 'search': search,
            'showing': showing, 'more_btn': more, 'area': area,
            'show_all': False, 'last_query': None,
        }

    def _show_all_programs(self, key):
        sec = self.prog_sections.get(key)
        if not sec:
            return
        sec['show_all'] = True
        self._update_prog_list(key)

    def _update_all_prog_lists(self):
        for key in self.prog_sections:
            self._update_prog_list(key)

    def _set_collecting(self, busy):
        self._collecting = busy
        self.refresh_btn.set_sensitive(not busy)
        self.footer_refresh_btn.set_sensitive(not busy)
        self.bios_full_btn.set_sensitive(not busy)
        self.hw_full_btn.set_sensitive(not busy)
        self.export_btn.set_sensitive(not busy)
        self.export_json_btn.set_sensitive(not busy)
        self.export_csv_btn.set_sensitive(not busy)
        self.copy_summary_btn.set_sensitive(not busy)
        self.save_snapshot_btn.set_sensitive(not busy)
        self.compare_btn.set_sensitive(not busy)
        if busy:
            self.spinner.start()
            self._set_status(i18n.t('xray.collecting'))
        else:
            self.spinner.stop()
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
                    'network': {'summary': '', 'details': ''},
                    'system': {'summary': '', 'details': ''},
                    'disks': [], 'alerts': [],
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

        network = snap.get('network') or {}
        system = snap.get('system') or {}
        self._network_detail_text = (
            network.get('details') or i18n.t('xray.unavailable'))
        system_text = system.get('details') or i18n.t('xray.unavailable')
        smart_known = snap.get('smart_known') or []
        if smart_known:
            lines = [system_text, '', '▸ ' + i18n.t('xray.smart_known')]
            for item in smart_known:
                label = item.get('overall_text') or item.get('overall') or 'unknown'
                lines.append(f"  • {item.get('disk','?')} — {label}")
            system_text = '\n'.join(lines)
        self._system_detail_text = system_text
        self._set_text_area(self.network_details, self._network_detail_text)
        self._set_text_area(self.system_details, self._system_detail_text)
        net_summary = network.get('summary') or ''
        sys_summary = system.get('summary') or ''
        self.network_card['subtitle'].set_text(net_summary)
        self.network_card['subtitle'].set_visible(bool(net_summary))
        self.system_card['subtitle'].set_text(sys_summary)
        self.system_card['subtitle'].set_visible(bool(sys_summary))

        alerts = snap.get('alerts') or []
        self._alert_texts = [a.get('text') for a in alerts if a.get('text')]
        if self._alert_texts:
            self.alerts_line.set_text(
                '⚠️ ' + '  ·  '.join(self._alert_texts))
            self.alerts_line.set_visible(True)
        else:
            self.alerts_line.set_visible(False)

        self.updated.set_text(i18n.t(
            'xray.updated_at', time=datetime.now().strftime('%H:%M')))
        self.updated.set_visible(True)

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
        gq = (self.global_search.get_text() or '').strip().lower()
        query = q + '\x00' + gq
        if sec.get('last_query') != query:
            sec['show_all'] = False
            sec['last_query'] = query

        def matches(item):
            haystack = ' '.join(str(part or '') for part in item).lower()
            return (not q or q in haystack) and (not gq or gq in haystack)

        filtered = [item for item in items if matches(item)]
        badge = sec['card']['badge']
        badge.set_text(str(len(items)))
        badge.set_visible(bool(items))
        total = len(filtered)
        if sec.get('show_all'):
            show = filtered
        else:
            show = filtered[: self.PROGRAM_RENDER_LIMIT]
        sec['more_btn'].set_visible(
            total > self.PROGRAM_RENDER_LIMIT and not sec.get('show_all'))
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


    def _export(self, kind):
        self._export_kind = kind
        if kind == 'json':
            title = i18n.t('xray.export_json_title')
            name = i18n.t('xray.export_json_filename')
        elif kind == 'csv':
            title = i18n.t('xray.export_csv_title')
            name = i18n.t('xray.export_csv_filename')
        else:
            title = i18n.t('xray.export_title')
            name = i18n.t('xray.export_filename')
        dialog = Gtk.FileDialog()
        dialog.set_title(title)
        dialog.set_initial_name(name)
        try:
            dialog.save(self, None, self._on_export_response)
        except Exception:
            self._write_export(Path.home() / name)

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

    def _set_export_buttons_sensitive(self, sensitive):
        self.export_btn.set_sensitive(sensitive)
        self.export_json_btn.set_sensitive(sensitive)
        self.export_csv_btn.set_sensitive(sensitive)

    def _write_export(self, path):
        if self._priv_bios and self._priv_hw:
            self._finish_export(path, None)
            return
        self._set_export_buttons_sensitive(False)
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
        self._set_export_buttons_sensitive(True)
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
            kind = getattr(self, '_export_kind', 'html')
            content = self._build_export_content(kind, priv_error)
            Path(path).write_text(content, encoding='utf-8')
            opened = False
            if kind == 'html':
                opened = self._open_report(path)
                body = i18n.t('xray.export_done_body', path=str(path))
                if opened:
                    body += '\n\n' + i18n.t('xray.export_opened')
            elif kind == 'json':
                body = i18n.t('xray.export_json_done_body', path=str(path))
            else:
                body = i18n.t('xray.export_csv_done_body', path=str(path))
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

    def _build_export_content(self, kind, priv_error=''):
        snap = self._snapshot or {}
        bios = snap.get('bios', {}) or {}
        hw = snap.get('hardware', {}) or {}
        kwargs = dict(
            bios_details=self._bios_detail_text or bios.get('details') or '',
            hw_details=self._hw_detail_text or hw.get('details') or '',
            bios_source=self._bios_source_text,
            hw_source=self._hw_source_text,
            priv_error=priv_error,
            redact=self.redact_check.get_active(),
        )
        if kind == 'json':
            return xray.build_report_json(snap, **kwargs)
        if kind == 'csv':
            return xray.build_report_csv(snap, **kwargs)
        return xray.build_report_html(snap, **kwargs)

    def _current_snapshot_data(self):
        snap = self._snapshot or {}
        bios = snap.get('bios', {}) or {}
        hw = snap.get('hardware', {}) or {}
        return xray.build_report_data(
            snap,
            bios_details=self._bios_detail_text or bios.get('details') or '',
            hw_details=self._hw_detail_text or hw.get('details') or '',
            bios_source=self._bios_source_text,
            hw_source=self._hw_source_text,
            redact=self.redact_check.get_active(),
        )

    def _save_snapshot(self):
        try:
            data = self._current_snapshot_data()
            path = snapshots.save_snapshot(data)
            show_info(self, i18n.t('xray.snapshot.saved'),
                      i18n.t('xray.snapshot.saved_body', path=str(path)))
            self._set_status(i18n.t('xray.snapshot.saved'))
        except Exception as exc:
            show_info(self, i18n.t('xray.export_error_title'),
                      i18n.t('xray.export_error_body', detail=str(exc)))

    def _open_compare(self):
        dialog = CompareSnapshotsDialog(self, current_provider=self._current_snapshot_data)
        dialog.present()

    def _build_export_html(self, priv_error=''):
        return self._build_export_content('html', priv_error)



class SpaceAnalysisDialog(Gtk.Window):
    """Análise de arquivos/pastas grandes e duplicados (revisão)."""

    def __init__(self, parent):
        super().__init__()
        self.set_title(i18n.t('space.title'))
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(760, 560)
        self.add_css_class('dialog')

        self._folder = str(Path.home())
        self._cancel = False
        self._busy = False

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(i18n.t('space.title'), 'dialog-title'))
        root.append(_txt(i18n.t('space.subtitle'), 'muted', wrap=True))

        folder_row = _hbox(8)
        folder_row.append(_txt(i18n.t('space.folder') + ':', 'cat-name'))
        self.folder_label = _txt(self._folder, 'muted', wrap=True)
        self.folder_label.set_hexpand(True)
        self.folder_label.set_xalign(0)
        folder_row.append(self.folder_label)
        choose = Gtk.Button(label=i18n.t('space.choose'))
        choose.add_css_class('btn-secondary')
        choose.connect('clicked', lambda *_: self._choose_folder())
        folder_row.append(choose)
        root.append(folder_row)

        controls = _hbox(8)
        self.scan_btn = Gtk.Button(label=i18n.t('space.scan'))
        self.scan_btn.add_css_class('btn-green')
        self.scan_btn.connect('clicked', lambda *_: self._start_scan())
        controls.append(self.scan_btn)
        self.cancel_btn = Gtk.Button(label=i18n.t('space.cancel'))
        self.cancel_btn.add_css_class('btn-secondary')
        self.cancel_btn.set_sensitive(False)
        self.cancel_btn.connect('clicked', lambda *_: self._request_cancel())
        controls.append(self.cancel_btn)
        spacer = Gtk.Box(); spacer.set_hexpand(True); controls.append(spacer)
        close = Gtk.Button(label=i18n.t('common.close'))
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        controls.append(close)
        root.append(controls)

        self.status = _txt(i18n.t('space.ready'), 'muted', wrap=True)
        root.append(self.status)

        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)

        self.large_box = _vbox(8)
        self.large_scroll = Gtk.ScrolledWindow()
        self.large_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.large_scroll.set_vexpand(True)
        self.large_scroll.set_child(self.large_box)
        self.notebook.append_page(self.large_scroll, Gtk.Label(label=i18n.t('space.tab.large')))

        self.dupes_box = _vbox(8)
        self.dupes_scroll = Gtk.ScrolledWindow()
        self.dupes_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.dupes_scroll.set_vexpand(True)
        self.dupes_scroll.set_child(self.dupes_box)
        self.notebook.append_page(self.dupes_scroll, Gtk.Label(label=i18n.t('space.tab.duplicates')))

        root.append(self.notebook)
        self.set_child(root)

    def _choose_folder(self):
        try:
            dialog = Gtk.FileDialog()
            dialog.set_title(i18n.t('space.choose'))
            def on_done(dlg, res):
                try:
                    folder = dlg.select_folder_finish(res)
                except Exception:
                    return
                if folder:
                    p = folder.get_path()
                    if p:
                        self._folder = p
                        self.folder_label.set_text(p)
            dialog.select_folder(self, None, on_done)
        except Exception:
            # fallback: no-op if not available
            pass

    def _request_cancel(self):
        self._cancel = True
        self.status.set_text(i18n.t('space.cancelled'))

    def _set_busy(self, busy):
        self._busy = busy
        self.scan_btn.set_sensitive(not busy)
        self.cancel_btn.set_sensitive(busy)

    def _clear_box(self, box):
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _open_path(self, path):
        target = path
        try:
            if os.path.isfile(path):
                target = os.path.dirname(path) or path
        except Exception:
            pass
        uri = GLib.filename_to_uri(target, None)
        try:
            Gtk.show_uri(self, uri, Gdk.CURRENT_TIME)
        except Exception:
            try:
                import subprocess
                subprocess.Popen(['xdg-open', target])
            except Exception:
                pass

    def _add_item_row(self, box, title, subtitle=''):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class('cat-row')
        info = _vbox(2)
        info.set_hexpand(True)
        info.append(_txt(title, 'cat-name', wrap=True))
        if subtitle:
            info.append(_txt(subtitle, 'muted', wrap=True))
        row.append(info)
        btn = Gtk.Button(label=i18n.t('space.open_folder'))
        btn.add_css_class('btn-secondary')
        btn.connect('clicked', lambda *_p, p=title: self._open_path(p))
        row.append(btn)
        box.append(row)

    def _start_scan(self):
        if self._busy:
            return
        self._cancel = False
        self._set_busy(True)
        self.status.set_text(i18n.t('space.scanning'))
        self._clear_box(self.large_box)
        self._clear_box(self.dupes_box)
        folder = self._folder
        threading.Thread(target=self._scan_work, args=(folder,), daemon=True).start()

    def _scan_work(self, folder):
        try:
            large = space.scan_largest(folder, top_files=40, top_dirs=25, cancel=lambda: self._cancel)
            if self._cancel:
                GLib.idle_add(self._apply_cancelled)
                return
            dupes = space.find_duplicates(folder, min_size=1024*1024, top_groups=30, cancel=lambda: self._cancel)
        except Exception as exc:
            GLib.idle_add(self._apply_error, str(exc))
            return
        if self._cancel or large.get('cancelled') or dupes.get('cancelled'):
            GLib.idle_add(self._apply_cancelled)
            return
        GLib.idle_add(self._apply_results, large, dupes)

    def _apply_cancelled(self):
        self._set_busy(False)
        self.status.set_text(i18n.t('space.cancelled'))
        return GLib.SOURCE_REMOVE

    def _apply_error(self, detail):
        self._set_busy(False)
        self.status.set_text(i18n.t('space.error'))
        self._clear_box(self.large_box)
        self.large_box.append(_txt(detail, 'muted', wrap=True))
        return GLib.SOURCE_REMOVE

    def _apply_results(self, large, dupes):
        self._set_busy(False)
        self.status.set_text(i18n.t('space.ready'))
        self._clear_box(self.large_box)
        self._clear_box(self.dupes_box)

        # large files
        self.large_box.append(_txt(i18n.t('space.large.files'), 'cat-name'))
        files = large.get('files') or []
        if not files:
            self.large_box.append(_txt(i18n.t('space.none'), 'muted'))
        else:
            for item in files:
                p = item.get('path') or ''
                sz = space.format_size(item.get('size') or 0)
                self._add_item_row(self.large_box, p, sz)
        # large dirs
        self.large_box.append(_txt(i18n.t('space.large.dirs'), 'cat-name'))
        dirs = large.get('dirs') or []
        if not dirs:
            self.large_box.append(_txt(i18n.t('space.none'), 'muted'))
        else:
            for item in dirs:
                p = item.get('path') or ''
                sz = space.format_size(item.get('size') or 0)
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.add_css_class('cat-row')
                info = _vbox(2); info.set_hexpand(True)
                info.append(_txt(p, 'cat-name', wrap=True))
                info.append(_txt(sz, 'muted', wrap=True))
                row.append(info)
                btn = Gtk.Button(label=i18n.t('space.open_folder'))
                btn.add_css_class('btn-secondary')
                btn.connect('clicked', lambda *_b, path=p: self._open_path(path))
                row.append(btn)
                self.large_box.append(row)

        # duplicates
        groups = dupes.get('groups') or []
        if not groups:
            self.dupes_box.append(_txt(i18n.t('space.dupes.none'), 'muted', wrap=True))
        else:
            for g in groups:
                header = i18n.t('space.dupes.group',
                                count=g.get('count', 0),
                                size=space.format_size(g.get('size') or 0),
                                wasted=space.format_size(g.get('wasted') or 0))
                self.dupes_box.append(_txt(header, 'cat-name', wrap=True))
                for fp in (g.get('files') or []):
                    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                    row.add_css_class('cat-row')
                    info = _vbox(2); info.set_hexpand(True)
                    info.append(_txt(fp, 'muted', wrap=True))
                    row.append(info)
                    btn = Gtk.Button(label=i18n.t('space.open_folder'))
                    btn.add_css_class('btn-secondary')
                    btn.connect('clicked', lambda *_b, path=fp: self._open_path(path))
                    row.append(btn)
                    self.dupes_box.append(row)
                sep = Gtk.Separator(); sep.set_margin_top(4); sep.set_margin_bottom(4)
                self.dupes_box.append(sep)
        return GLib.SOURCE_REMOVE

