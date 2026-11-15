#!/usr/bin/env python3
"""Diálogos do Cleanix: avisos, confirmação, detalhes e histórico."""

import logging
import os
import subprocess
import threading
from collections import namedtuple
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk, Pango

from . import autostart, history, systeminfo

log = logging.getLogger(__name__)

# PATH usado quando o comando roda via pkexec (root não herda o ambiente).
SYSTEM_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
COMMAND_TIMEOUT = 600  # segundos

Result = namedtuple('Result', 'ok output error')

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


def _friendly_error(text):
    """Traduz os erros mais comuns do pkexec para uma linguagem simples."""
    if not text:
        return ''
    if 'Not authorized' in text or 'dismissed' in text.lower():
        return ('A senha de administrador não foi informada.\n'
                'Nada foi alterado no sistema.')
    if 'No such file or directory' in text and 'bash' in text:
        return 'Não foi possível iniciar o shell do sistema.'
    return text


def execute_command(command, as_root=False, timeout=COMMAND_TIMEOUT):
    """Executa ``command`` num shell e devolve um ``Result``.

    Roda sempre em uma thread separada (quem chama cuida disso), nunca
    levanta exceção e registra tudo no log do Cleanix.

    ``as_root=True`` usa o ``pkexec``, que abre a janela gráfica de senha do
    sistema operacional.
    """
    if as_root:
        argv = ['pkexec', '/usr/bin/bash', '-c', command]
    else:
        argv = ['/usr/bin/bash', '-c', command]

    env = dict(os.environ)
    env['PATH'] = SYSTEM_PATH + ':' + env.get('PATH', '')

    log.info('Executando (root=%s): %s', as_root, command)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except FileNotFoundError as exc:
        log.error('Programa não encontrado ao executar %r: %s', command, exc)
        return Result(False, '', f'Programa não encontrado: {exc}')
    except subprocess.TimeoutExpired:
        log.error('Tempo esgotado ao executar %r', command)
        return Result(False, '',
                      f'O comando demorou mais de {timeout} segundos '
                      'e foi cancelado.')
    except Exception as exc:  # noqa: BLE001 - o erro precisa chegar ao usuário
        log.exception('Falha inesperada ao executar %r', command)
        return Result(False, '', f'Falha inesperada: {exc}')

    ok = proc.returncode == 0
    output = (proc.stdout or '').strip()
    error = (proc.stderr or '').strip()

    if ok:
        log.info('Concluído (código %s): %s', proc.returncode, command)
    else:
        log.warning('Falhou (código %s): %s -> %s',
                    proc.returncode, command, error)
        error = _friendly_error(error) or (
            f'O comando terminou com código {proc.returncode}.')

    return Result(ok, output, error)


def _limit(text, size=1500):
    if len(text) <= size:
        return text
    return text[:size] + '\n…'


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


class _ActionDialog(Gtk.Window):
    """Base para diálogos que executam comandos do sistema."""

    heading = ''
    subtitle = ''
    actions = ()

    def __init__(self, parent):
        super().__init__()
        self._buttons = {}
        self.set_title(self.heading)
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(560, -1)
        self.add_css_class('dialog')

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt(self.heading, 'dialog-title'))
        if self.subtitle:
            root.append(_txt(self.subtitle, 'muted', wrap=True))

        for action in self.actions:
            root.append(self._action_row(action))

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        self.status = _txt('', 'muted', wrap=True)
        root.append(self.status)

        close = Gtk.Button(label='Fechar')
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        root.append(close)

        self.set_child(root)

    def _action_row(self, action):
        row = _hbox(10)
        row.add_css_class('dialog-row')

        button = Gtk.Button(label=action['label'])
        button.add_css_class('btn-green')
        if action.get('dialog') is not None:
            button.connect('clicked', lambda *_: action['dialog'](self))
        else:
            button.connect('clicked', self._on_clicked, action)
        row.append(button)
        self._buttons[action['label']] = button

        description = _txt(action['description'], 'cat-name')
        description.set_hexpand(True)
        description.set_valign(Gtk.Align.CENTER)
        description.set_wrap(True)
        row.append(description)
        return row

    def _on_clicked(self, button, action):
        log.info('Ação escolhida: %s', action['label'])
        confirm(self, f'Confirmar: {action["label"]}', action['detail'],
                'Executar', lambda: self._start(button, action))

    def _start(self, button, action):
        label = button.get_label()
        button.set_label('Executando…')
        button.set_sensitive(False)
        self.status.set_text(f'{action["label"]}: executando…')

        def work():
            result = execute_command(action['command'], action['as_root'])
            GLib.idle_add(self._done, button, label, action, result)

        threading.Thread(target=work, daemon=True, name='cleanix-action').start()

    def _done(self, button, label, action, result):
        button.set_label(label)
        button.set_sensitive(True)

        if result.ok:
            self.status.set_text(f'{action["label"]}: concluído.')
            body = result.output or 'Nada havia para fazer — o sistema já ' \
                                    'estava otimizado.'
            show_info(self, f'{action["label"]}: concluído', _limit(body))
        else:
            self.status.set_text(f'{action["label"]}: não concluído.')
            show_info(self, f'{action["label"]}: não concluído',
                      _limit(result.error or 'O comando não foi concluído.'))
        return GLib.SOURCE_REMOVE


OPTIMIZER_ACTIONS = (
    {
        'label': 'APT Auto-clean',
        'description': 'Remove pacotes órfãos e limpa o cache do APT',
        'detail': 'Serão removidos automaticamente os pacotes que não são '
                  'mais necessários e o cache do APT será limpo.\n'
                  'Será pedida a senha de administrador.',
        'command': 'apt-get autoremove -y && apt-get clean',
        'as_root': True,
    },
    {
        'label': 'Journal Vacuum',
        'description': 'Reduz os logs do sistema aos últimos 7 dias',
        'detail': 'Os logs antigos do systemd (journalctl) serão apagados, '
                  'liberando espaço em disco.\n'
                  'Será pedida a senha de administrador.',
        'command': 'journalctl --vacuum-time=7d',
        'as_root': True,
    },
    {
        'label': 'fstrim',
        'description': 'Otimiza o descarte de blocos livres no disco',
        'detail': 'O sistema avisará ao disco quais blocos estão livres, o '
                  'que ajuda no desempenho do SSD.\n'
                  'Será pedida a senha de administrador.',
        'command': 'fstrim -av',
        'as_root': True,
    },
)


ADJUSTMENT_ACTIONS = (
    {
        'label': 'Desktop',
        'description': 'Ativa as animações da interface do GNOME',
        'detail': 'As animações de janelas e menus do GNOME serão ativadas.',
        'command': 'gsettings set org.gnome.desktop.interface '
                   'enable-animations true',
        'as_root': False,
    },
    {
        'label': 'Privacidade',
        'description': 'Esvazia lixeira e temporários antigos automaticamente',
        'detail': 'O GNOME passará a esvaziar a lixeira e a remover arquivos '
                  'temporários antigos automaticamente.',
        'command': 'gsettings set org.gnome.desktop.privacy '
                   'remove-old-trash-files true && '
                   'gsettings set org.gnome.desktop.privacy '
                   'remove-old-temp-files true',
        'as_root': False,
    },
    {
        'label': 'Performance',
        'description': 'Desativa animações para deixar o sistema mais rápido',
        'detail': 'As animações de janelas e menus do GNOME serão desativadas, '
                  'deixando a interface mais leve em computadores modestos.',
        'command': 'gsettings set org.gnome.desktop.interface '
                   'enable-animations false',
        'as_root': False,
    },
)


class StartupAppsDialog(Gtk.Window):
    """Ativa e desativa os aplicativos que iniciam junto com o sistema."""

    def __init__(self, parent):
        super().__init__()
        self.set_title('Aplicativos de Inicialização')
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(560, -1)
        self.add_css_class('dialog')

        root = _vbox(10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        root.append(_txt('Aplicativos de Inicialização', 'dialog-title'))
        root.append(_txt('Desative o que não precisa abrir junto com o '
                         'sistema. A mudança vale só para o seu usuário e '
                         'não precisa de senha.', 'muted', wrap=True))

        self._list = _vbox(2)
        root.append(self._list)

        self.status = _txt('', 'muted', wrap=True)
        root.append(self.status)

        separator = Gtk.Separator()
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        root.append(separator)

        close = Gtk.Button(label='Fechar')
        close.add_css_class('btn-secondary')
        close.connect('clicked', lambda *_: self.close())
        root.append(close)

        self.set_child(root)
        self._restoring = False
        self._entries = []
        self._load()

    def _clear(self):
        while True:
            child = self._list.get_first_child()
            if child is None:
                break
            self._list.remove(child)

    def _load(self):
        self._clear()
        try:
            self._entries = autostart.list_entries(Path.home())
        except OSError as exc:
            log.exception('Falha ao listar aplicativos de inicialização')
            self._entries = []
            show_info(self, 'Não foi possível ler os aplicativos',
                      f'Detalhe: {exc}')

        if not self._entries:
            self._list.append(_txt('Nenhum aplicativo de inicialização '
                                   'encontrado.', 'empty-text'))
            return

        for entry in self._entries:
            self._list.append(self._row(entry))

    def _row(self, entry):
        row = _hbox(10)
        row.add_css_class('dialog-row')

        info = _vbox(1)
        info.set_hexpand(True)
        info.append(_txt(entry.name, 'cat-name'))
        if entry.command:
            info.append(_txt(entry.command, 'muted'))
        row.append(info)

        switch = Gtk.Switch()
        switch.set_active(not entry.hidden)
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect('notify::active', self._on_toggle, entry)
        row.append(switch)
        return row

    def _on_toggle(self, switch, _pspec, entry):
        if self._restoring:
            return
        enabled = switch.get_active()
        try:
            autostart.set_enabled(entry, enabled, Path.home())
        except OSError as exc:
            log.exception('Falha ao alterar o aplicativo %s', entry.name)
            show_info(self, 'Não foi possível alterar',
                      f'{entry.name}: {exc}')
            self._restoring = True
            switch.set_active(not enabled)
            self._restoring = False
            return

        estado = 'ativado' if enabled else 'desativado'
        log.info('Startup %s: %s', entry.name, estado)
        self.status.set_text(f'{entry.name}: {estado}.')


class OptimizerDialog(_ActionDialog):
    """Otimizador do sistema, com ações que realmente são executadas."""

    heading = 'Otimizador do Sistema'
    subtitle = ('Escolha uma ação. Nada é executado sem a sua confirmação e, '
                'quando necessário, será pedida a senha de administrador.')
    actions = OPTIMIZER_ACTIONS + (
        {
            'label': 'Startup Apps',
            'description': 'Veja e desative o que inicia junto com o sistema',
            'dialog': lambda parent: StartupAppsDialog(parent).present(),
        },
    )


class AdjustmentsDialog(_ActionDialog):
    """Ajustes do sistema, aplicados com gsettings (sem root)."""

    heading = 'Ajustes do Sistema'
    subtitle = ('Estes ajustes valem apenas para o seu usuário e não precisam '
                'de senha de administrador.')
    actions = ADJUSTMENT_ACTIONS


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
