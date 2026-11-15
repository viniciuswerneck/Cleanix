#!/usr/bin/env python3
"""Janela principal do Cleanix, fiel ao mockup e alimentada por dados reais."""

import os
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango

from . import charts, dialogs, history, memory, scanner, settings, systeminfo

CATEGORY_COLORS = ('#3295F5', '#20C957', '#F4510B', '#914CF5', '#F5A623')
HEALTH_TEXTS = {
    'ok': ('Seu sistema está saudável!', '#25CE60', '✓',
           'Nenhum problema crítico encontrado.', 'ok-text',
           'Tudo funcionando bem!'),
    'warn': ('Atenção: pouco espaço em disco', '#F5A623', '!',
             'Considere liberar espaço em disco.', 'warn-text',
             'Pouco espaço livre'),
    'bad': ('Espaço em disco crítico!', '#F4510B', '×',
            'Libere espaço o quanto antes.', 'bad-text',
            'Espaço em disco crítico'),
}


# ---- helpers -------------------------------------------------------------

def txt(text, cls=None, halign=Gtk.Align.START, wrap=False, width=None):
    lbl = Gtk.Label()
    lbl.set_text(text)
    lbl.set_halign(halign)
    lbl.set_xalign(0.0 if halign != Gtk.Align.CENTER else 0.5)
    if wrap:
        lbl.set_wrap(True)
        lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if width is not None:
        lbl.set_max_width_chars(width)
    if cls:
        lbl.add_css_class(cls)
    return lbl


def markup(text, cls=None, halign=Gtk.Align.START):
    lbl = Gtk.Label()
    lbl.set_markup(text)
    lbl.set_halign(halign)
    if halign == Gtk.Align.CENTER:
        lbl.set_justify(Gtk.Justification.CENTER)
    if cls:
        lbl.add_css_class(cls)
    return lbl


def emoji(char, cls=None):
    lbl = Gtk.Label()
    lbl.set_text(char)
    lbl.set_halign(Gtk.Align.CENTER)
    lbl.set_valign(Gtk.Align.CENTER)
    if cls:
        lbl.add_css_class(cls)
    return lbl


def vbox(spacing=4, **kw):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, **kw)


def hbox(spacing=8, **kw):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing, **kw)


def vsep():
    s = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
    s.set_margin_top(6)
    s.set_margin_bottom(6)
    return s


def sidebar_icon(name):
    img = Gtk.Image.new_from_icon_name(name)
    img.set_pixel_size(22)
    img.add_css_class('side-icon')
    return img


def split_size(text):
    """Separa '2,48 GB' em ('2,48', 'GB')."""
    parts = text.split(' ', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return text, ''


def plural(count, singular, plural_form):
    return f'{count} {singular if count == 1 else plural_form}'


class CleanixWindow(Gtk.ApplicationWindow):

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title('Cleanix')
        self.set_decorated(False)          # custom title bar

        self.categories = scanner.build_categories()
        self.selected = {c.key for c in self.categories if not c.requires_admin}
        self.results = {}
        self.scan_time = None
        self._busy = False
        self._syncing = False
        self._cpu_sample = None
        self._line_values = []
        self._memory_values = []
        self.cat_rows = {}
        self.history_rows = []
        self.metric_labels = {}
        self.metric_bars = {}
        self.action_buttons = []

        self._setup_css()
        self._build_ui()
        self._fit_to_screen()

        GLib.timeout_add(500, self._start_scan)
        GLib.timeout_add(2000, self._tick_cpu)

    def _fit_to_screen(self):
        """Make sure the window fits the usable screen area (workarea),
        so it never goes off-screen or behind the Ubuntu top panel."""
        display = Gdk.Display.get_default()
        monitor = None
        if display is not None:
            monitors = display.get_monitors()
            if monitors is not None and monitors.get_n_items() > 0:
                monitor = monitors.get_item(0)

        if monitor is None:
            self.set_default_size(1280, 800)
            return

        geo = monitor.get_geometry()
        width = max(1100, min(1536, geo.width))
        height = max(680, min(1040, geo.height))
        self.set_default_size(width, height)

        # On screens smaller than the design size, maximize so the window
        # fits exactly the usable workarea (below the top bar, above the dock).
        if geo.width < 1536 or geo.height < 1040:
            self.maximize()

    # ---- CSS ----
    def _setup_css(self):
        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(str(Path(__file__).with_name('styles.css')))
        except Exception as e:
            print('CSS error:', e)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ---- layout ----
    def _build_ui(self):
        root = vbox(0)
        self.set_child(root)

        root.append(self._top_bar())

        body = hbox(0)
        body.set_vexpand(True)
        body.set_hexpand(True)
        root.append(body)
        body.append(self._sidebar())
        body.append(self._content())

        root.append(self._status_bar())

    # ---- top bar ----
    def _top_bar(self):
        bar = hbox(12)
        bar.add_css_class('topbar')

        bar.append(emoji('🧹', 'app-logo'))

        names = vbox(0)
        names.set_valign(Gtk.Align.CENTER)
        names.append(txt('Cleanix', 'app-name'))
        names.append(txt('Seu sistema sempre em ótima forma', 'app-sub'))
        bar.append(names)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        btn_min = Gtk.Button(label='–')
        btn_min.add_css_class('win-btn')
        btn_min.connect('clicked', lambda *_: self.minimize())

        btn_max = Gtk.Button(label='▢')
        btn_max.add_css_class('win-btn')
        btn_max.connect('clicked', lambda *_: self._toggle_max())

        btn_close = Gtk.Button(label='✕')
        btn_close.add_css_class('win-close')
        btn_close.connect('clicked', lambda *_: self.close())

        for b in (btn_min, btn_max, btn_close):
            b.set_valign(Gtk.Align.CENTER)
            bar.append(b)
        return bar

    def _toggle_max(self):
        if self.is_maximized():
            self.unmaximize()
        else:
            self.maximize()

    # ---- sidebar ----
    def _sidebar(self):
        side = vbox(4)
        side.add_css_class('sidebar')
        side.set_size_request(228, -1)

        items = [
            ('Início', 'go-home-symbolic', '', True, None),
            ('Cleaner', 'edit-clear-symbolic', '(Limpeza)', False,
             lambda *_: self._open_details()),
            ('Optimizer', 'utilities-system-monitor-symbolic', '(Otimização)',
             False, lambda *_: self._open_optimizer()),
            ('Adjustments', 'emblem-system-symbolic', '(Ajustes)', False,
             lambda *_: self._open_adjustments()),
        ]
        for name, icon, sub, active, on_click in items:
            side.append(self._side_item(name, icon, sub, active, on_click))

        sep = Gtk.Separator()
        sep.add_css_class('side-sep')
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        side.append(sep)

        for name, icon, sub, active, on_click in [
            ('Histórico', 'document-open-symbolic', '', False,
             lambda *_: self._open_history()),
            ('Sobre', 'help-about-symbolic', '', False,
             lambda *_: self._show_about()),
        ]:
            side.append(self._side_item(name, icon, sub, active, on_click))

        expand = Gtk.Box()
        expand.set_vexpand(True)
        side.append(expand)

        ubuntu = vbox(2)
        ubuntu.set_margin_top(8)
        ubuntu.set_halign(Gtk.Align.CENTER)
        ubuntu.append(emoji('⬤', 'ubuntu-logo'))
        ubuntu.append(txt('Ubuntu', 'ubuntu-name', halign=Gtk.Align.CENTER))
        ubuntu.append(txt('22.04 LTS', 'ubuntu-ver', halign=Gtk.Align.CENTER))
        side.append(ubuntu)
        return side

    def _side_item(self, name, icon, sub, active, on_click=None):
        btn = Gtk.Button()
        btn.add_css_class('side-item')
        if active:
            btn.add_css_class('side-active')

        row = hbox(12)
        row.append(sidebar_icon(icon))

        labels = vbox(0)
        labels.set_valign(Gtk.Align.CENTER)
        labels.append(txt(name, 'side-title'))
        if sub:
            labels.append(txt(sub, 'side-sub'))
        row.append(labels)

        btn.set_child(row)
        if on_click is not None:
            btn.connect('clicked', on_click)
        return btn

    # ---- content ----
    def _content(self):
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)

        content = vbox(16)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        scroller.set_child(content)

        content.append(self._block_health())
        content.append(self._block_memory())
        content.append(self._block_cards())
        content.append(self._block_actions())
        content.append(self._block_bottom())
        return scroller

    # ---- Bloco 1: saúde ----
    def _block_health(self):
        card = hbox(16)
        card.add_css_class('card')

        geral = hbox(18)
        self.health_ring = charts.make_health_ring(128)
        geral.append(self.health_ring)

        info = vbox(4)
        info.set_valign(Gtk.Align.CENTER)
        self.health_title = txt('Seu sistema está saudável!', 'h1')
        info.append(self.health_title)
        self.last_check_label = txt('Ainda não verificado', 'sub')
        info.append(self.last_check_label)

        ok = hbox(6)
        self.health_icon = markup('<span foreground="#25CE60">✓</span>')
        ok.append(self.health_icon)
        self.health_text = txt('Nenhum problema crítico encontrado.',
                               'ok-text')
        ok.append(self.health_text)
        info.append(ok)

        geral.append(info)
        geral.set_hexpand(True)
        card.append(geral)

        card.append(vsep())
        card.append(self._metric('disk', '🗄️', 'Disco Livre', '#20C957'))
        card.append(vsep())
        card.append(self._metric('mem', '🟩', 'Memória', '#3295F5'))
        card.append(vsep())
        card.append(self._metric('cpu', '🟪', 'CPU', '#914CF5'))
        return card

    def _metric(self, key, icon, label, color):
        box = vbox(4)
        box.set_size_request(120, -1)

        head = hbox(8)
        head.append(emoji(icon))
        head.append(txt(label, 'metric-label'))
        box.append(head)

        value = txt('—', 'metric-value')
        pct = txt('', 'metric-pct')
        box.append(value)
        box.append(pct)

        bar = charts.make_bar(0.0, color, width=140, height=14)
        bar.set_margin_top(4)
        box.append(bar)

        self.metric_labels[key] = (value, pct)
        self.metric_bars[key] = bar
        return box

    # ---- Painel: memória RAM ----
    def _block_memory(self):
        card = vbox(10)
        card.add_css_class('card')

        head = hbox(8)
        head.append(emoji('🧠'))
        head.append(txt('Memória RAM', 'card-title'))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)

        self.memory_release_btn = Gtk.Button(label='Liberar memória')
        self.memory_release_btn.add_css_class('btn-secondary')
        self.memory_release_btn.connect('clicked',
                                        lambda *_: self._open_memory())
        head.append(self.memory_release_btn)
        card.append(head)

        body = hbox(18)

        info = vbox(2)
        info.set_size_request(230, -1)
        info.set_valign(Gtk.Align.CENTER)
        self.memory_panel_value = txt('—', 'big-number')
        info.append(self.memory_panel_value)
        self.memory_panel_sub = txt('Lendo a memória...', 'muted')
        info.append(self.memory_panel_sub)

        stats = hbox(16)
        stats.set_margin_top(4)
        self.memory_available_label = txt('Disponível: —', 'muted')
        self.memory_cache_label = txt('Cache: —', 'muted')
        stats.append(self.memory_available_label)
        stats.append(self.memory_cache_label)
        info.append(stats)
        body.append(info)

        chart_box = vbox(2)
        chart_box.set_hexpand(True)
        chart_box.set_valign(Gtk.Align.CENTER)
        self.memory_chart = charts.make_line_chart(
            width=320, height=96, color='#3295F5')
        self.memory_chart.set_values([])
        chart_box.append(self.memory_chart)
        body.append(chart_box)

        card.append(body)
        return card

    def _refresh_memory_panel(self, mem=None):
        mem = mem or systeminfo.get_mem_info()
        values = memory.read_meminfo()
        cache = memory.reclaimable_memory(values)

        self.memory_panel_value.set_text(systeminfo.format_bytes(mem.used))
        self.memory_panel_sub.set_text(
            f'de {systeminfo.format_bytes(mem.total)} · '
            f'{mem.percent_used:.0f}% em uso')
        self.memory_available_label.set_text(
            f'Disponível: {systeminfo.format_bytes(mem.available)}')
        self.memory_cache_label.set_text(
            f'Cache: {systeminfo.format_bytes(cache)}')

        self._memory_values.append(mem.percent_used / 100.0)
        self._memory_values = self._memory_values[-30:]
        self.memory_chart.set_values(self._memory_values)

    def _open_memory(self):
        dialog = dialogs.MemoryDialog(
            self, on_released=self._refresh_memory_panel)
        dialog.present()

    # ---- Bloco 2: três cartões ----
    def _block_cards(self):
        row = hbox(16)

        # ---- Cartão A: Espaço recuperável ----
        a = vbox(10)
        a.add_css_class('card')
        a.set_size_request(320, -1)

        a_top = hbox(14)
        a_top.append(emoji('🗑️', 'app-logo'))  # large trash
        a_info = vbox(2)
        a_info.set_valign(Gtk.Align.CENTER)
        a_info.append(txt('Espaço Recuperável', 'card-title'))
        self.recoverable_label = txt('—', 'big-number')
        a_info.append(self.recoverable_label)
        self.recoverable_sub = txt('Calculando...', 'muted')
        a_info.append(self.recoverable_sub)
        a_top.append(a_info)
        a.append(a_top)

        self.details_btn = Gtk.Button()
        self.details_btn.add_css_class('btn-green')
        bcontent = hbox(8)
        bcontent.set_halign(Gtk.Align.CENTER)
        bcontent.append(emoji('🔍'))
        bcontent.append(txt('Ver Detalhes...', halign=Gtk.Align.CENTER))
        self.details_btn.set_child(bcontent)
        self.details_btn.connect('clicked', lambda *_: self._open_details())
        a.append(self.details_btn)
        row.append(a)

        # ---- Cartão B: Uso do disco ----
        b = vbox(10)
        b.add_css_class('card')
        b.set_hexpand(True)

        b_head = hbox(8)
        b_head.append(emoji('🥧'))
        b_head.append(txt('Uso do Disco', 'card-title'))
        b.append(b_head)

        b_mid = hbox(16)
        self.disk_donut = charts.make_donut(
            [(0.5, '#3295F5'), (0.5, '#20C957')],
            center_markup="<span size='x-large' weight='bold'>—</span>",
            size=150, thickness=22)
        b_mid.append(self.disk_donut)

        legend = vbox(10)
        legend.set_valign(Gtk.Align.CENTER)
        l1 = hbox(8)
        l1.append(markup('<span foreground="#3295F5">●</span>'))
        self.disk_used_label = txt('Usado   —', 'legend')
        l1.append(self.disk_used_label)
        l2 = hbox(8)
        l2.append(markup('<span foreground="#20C957">●</span>'))
        self.disk_free_label = txt('Livre   —', 'legend')
        l2.append(self.disk_free_label)
        legend.append(l1)
        legend.append(l2)
        b_mid.append(legend)
        b.append(b_mid)

        self.disk_total_label = txt('Total: —', 'muted')
        b.append(self.disk_total_label)
        row.append(b)

        # ---- Cartão C: Sistema ----
        c = vbox(10)
        c.add_css_class('card')
        c.set_hexpand(True)

        c_head = hbox(8)
        c_head.append(emoji('📈'))
        c_head.append(txt('Sistema', 'card-title'))
        c.append(c_head)

        self.line_chart = charts.make_line_chart(width=180, height=120)
        self.line_chart.set_values([])
        c.append(self.line_chart)

        strip = hbox(8)
        strip.add_css_class('sys-strip')
        self.system_strip_icon = markup('<span foreground="#25CE60">✓</span>')
        strip.append(self.system_strip_icon)
        self.system_strip_text = txt('Tudo funcionando bem!', 'ok-text')
        strip.append(self.system_strip_text)
        c.append(strip)
        row.append(c)
        return row

    # ---- Bloco 3: ações ----
    def _block_actions(self):
        card = vbox(14)
        card.add_css_class('card')

        title = hbox(8)
        title.append(emoji('🧹'))
        title.append(txt('O que deseja fazer?', 'h1'))
        card.append(title)

        row = hbox(14)

        clean = self._action('🧹', 'Limpeza Inteligente',
                             'Remova arquivos temporários, caches e lixo do sistema.',
                             selected=True)
        clean.connect('clicked', lambda *_: self._open_details())
        self.action_buttons.append(clean)
        row.append(clean)

        optimize = self._action('🚀', 'Otimização',
                                'Melhore o desempenho do seu Ubuntu.')
        optimize.connect('clicked', lambda *_: self._open_optimizer())
        self.action_buttons.append(optimize)
        row.append(optimize)

        adjust = self._action('🎛️', 'Ajustes',
                              'Personalize e ajuste seu sistema com segurança.')
        adjust.connect('clicked', lambda *_: self._open_adjustments())
        self.action_buttons.append(adjust)
        row.append(adjust)

        card.append(row)
        return card

    def _action(self, icon, title, desc, selected=False):
        btn = Gtk.Button()
        btn.add_css_class('action-card')
        if selected:
            btn.add_css_class('action-sel')

        row = hbox(12)
        row.append(emoji(icon, 'action-icon'))

        info = vbox(3)
        info.set_valign(Gtk.Align.CENTER)
        info.set_hexpand(True)
        info.append(txt(title, 'action-title'))
        info.append(txt(desc, 'action-desc', wrap=True, width=26))
        row.append(info)

        row.append(emoji('→', 'arrow-circle'))
        btn.set_child(row)
        return btn

    # ---- Bloco 4: informações ----
    def _block_bottom(self):
        row = hbox(16)

        # ---- Categorias ----
        a = vbox(10)
        a.add_css_class('card')
        a.set_size_request(520, -1)
        a.append(txt('Categorias de Limpeza', 'card-title'))

        inner = hbox(18)
        self.cat_list = vbox(8)
        self.cat_list.set_hexpand(True)

        for cat in self.categories:
            r = hbox(10)
            check = Gtk.CheckButton()
            check.set_active(cat.key in self.selected)
            check.set_valign(Gtk.Align.CENTER)
            if cat.requires_admin:
                check.set_tooltip_text('Precisa da senha de administrador')
            check.connect('toggled', self._on_cat_toggle, cat.key)
            r.append(check)
            r.append(emoji(dialogs.CATEGORY_ICONS.get(cat.key, '📁')))

            name_lbl = txt(cat.label, 'cat-name')
            name_lbl.set_hexpand(True)
            r.append(name_lbl)

            size_lbl = txt('—', 'cat-size')
            r.append(size_lbl)

            self.cat_rows[cat.key] = (check, size_lbl)
            self.cat_list.append(r)

        inner.append(self.cat_list)

        self.cat_donut = charts.make_donut(
            [(1.0, '#2B2938')],
            center_markup="<span size='large' weight='bold'>—</span>",
            size=125, thickness=20)
        inner.append(self.cat_donut)
        a.append(inner)
        row.append(a)

        # ---- Últimas ações ----
        b = vbox(10)
        b.add_css_class('card')
        b.set_hexpand(True)

        head = hbox(8)
        head.append(emoji('🕘'))
        head.append(txt('Últimas Ações', 'card-title'))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)
        self.history_btn = Gtk.Button(label='Ver Histórico →')
        self.history_btn.add_css_class('link-btn')
        self.history_btn.connect('clicked', lambda *_: self._open_history())
        head.append(self.history_btn)
        b.append(head)

        self.history_list = vbox(8)
        b.append(self.history_list)
        row.append(b)
        return row

    # ---- status bar ----
    def _status_bar(self):
        bar = hbox(10)
        bar.add_css_class('statusbar')

        bar.append(markup('<span foreground="#25CE60">✓</span>'))
        self.status_text = txt('Pronto para ajudar seu sistema!', 'status-text')
        bar.append(self.status_text)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        cfg = Gtk.Button()
        cfg.add_css_class('status-btn')
        cfg_c = hbox(6)
        cfg_c.append(emoji('⚙️'))
        cfg_c.append(txt('Configurações'))
        cfg.set_child(cfg_c)
        cfg.connect('clicked', lambda *_: self._show_settings())
        bar.append(cfg)

        help_b = Gtk.Button()
        help_b.add_css_class('status-btn')
        help_c = hbox(6)
        help_c.append(emoji('❓'))
        help_c.append(txt('Ajuda'))
        help_b.set_child(help_c)
        help_b.connect('clicked', lambda *_: self._show_help())
        bar.append(help_b)
        return bar

    # ---- varredura ----
    def _start_scan(self):
        if self._busy:
            return False
        self._set_busy(True)
        self.status_text.set_text('Escaneando...')
        threading.Thread(target=self._scan_worker, daemon=True).start()
        return False

    def _scan_worker(self):
        try:
            results = scanner.scan_all(self.categories)
        except Exception as exc:  # pragma: no cover - falha inesperada
            GLib.idle_add(self._scan_failed, str(exc))
            return
        GLib.idle_add(self._scan_done, results)

    def _scan_failed(self, message):
        self.status_text.set_text('Não foi possível concluir a varredura')
        self._set_busy(False)
        dialogs.show_info(self, 'Falha na varredura',
                          f'Ocorreu um erro ao analisar o sistema:\n{message}')
        return False

    def _scan_done(self, results):
        self.results = results
        self.scan_time = datetime.now()

        available = {key for key, res in results.items() if res.available}
        self.selected &= available

        try:
            self._refresh_system()
            self._refresh_recoverable()
            self._refresh_categories()
            self._refresh_history()
        finally:
            self._set_busy(False)

        self.status_text.set_text('Pronto para ajudar seu sistema!')
        return False

    def _refresh_system(self):
        disk = systeminfo.get_disk_info('/')
        free_pct = 100.0 - disk.percent_used
        state = systeminfo.health_state(free_pct)
        self._set_health(state)

        if self.scan_time is not None:
            self.last_check_label.set_text(
                f'Última verificação: hoje às {self.scan_time:%H:%M}')

        total = disk.total or 1

        value, pct = self.metric_labels['disk']
        value.set_text(systeminfo.format_bytes(disk.free))
        pct.set_text(f'({free_pct:.0f}% livre)')
        self.metric_bars['disk'].set_fraction(disk.free / total)

        mem = systeminfo.get_mem_info()
        value, pct = self.metric_labels['mem']
        value.set_text(systeminfo.format_bytes(mem.used))
        pct.set_text(f'({mem.percent_used:.0f}%)')
        self.metric_bars['mem'].set_fraction(mem.percent_used / 100.0)
        self._refresh_memory_panel(mem)

        cores = os.cpu_count() or 1
        _, cpu_pct = self.metric_labels['cpu']
        cpu_pct.set_text(f'({plural(cores, "núcleo", "núcleos")})')

        used_frac = disk.used / total
        free_frac = disk.free / total
        self.disk_donut.set_segments(
            [(used_frac, '#3295F5'), (free_frac, '#20C957')],
            center_markup=(f"<span size='x-large' weight='bold'>"
                           f"{disk.percent_used:.0f}%</span>"))
        self.disk_used_label.set_text(
            f'Usado   {systeminfo.format_bytes(disk.used)}')
        self.disk_free_label.set_text(
            f'Livre   {systeminfo.format_bytes(disk.free)}')
        self.disk_total_label.set_text(
            f'Total: {systeminfo.format_bytes(disk.total)}')

    def _set_health(self, state):
        title, color, glyph, message, cls, strip = HEALTH_TEXTS[state]
        self.health_ring.set_state(state)
        self.health_title.set_text(title)
        self.health_icon.set_markup(f'<span foreground="{color}">{glyph}</span>')
        self.health_text.set_text(message)
        for name in ('ok-text', 'warn-text', 'bad-text'):
            self.health_text.remove_css_class(name)
        self.health_text.add_css_class(cls)

        self.system_strip_icon.set_markup(
            f'<span foreground="{color}">{glyph}</span>')
        self.system_strip_text.set_text(strip)
        for name in ('ok-text', 'warn-text', 'bad-text'):
            self.system_strip_text.remove_css_class(name)
        self.system_strip_text.add_css_class(cls)

    def _recoverable_total(self):
        cats = {c.key: c for c in self.categories}
        total = 0
        for key, res in self.results.items():
            cat = cats.get(key)
            if cat is not None and res.available:
                total += res.bytes
        return total

    def _refresh_recoverable(self):
        total = self._recoverable_total()

        self.recoverable_label.set_text(systeminfo.format_bytes(total))
        if total:
            self.recoverable_sub.set_text('Arquivos desnecessários encontrados')
        else:
            self.recoverable_sub.set_text(
                'Nenhum arquivo desnecessário encontrado')
        self._refresh_cat_donut(total)

    def _refresh_cat_donut(self, total):
        if total <= 0:
            self.cat_donut.set_segments(
                [(1.0, '#2B2938')],
                center_markup="<span size='large' weight='bold'>0 B</span>")
            return

        segments = []
        for index, cat in enumerate(self.categories):
            res = self.results.get(cat.key)
            if res is None or not res.available or res.bytes <= 0:
                continue
            color = CATEGORY_COLORS[index % len(CATEGORY_COLORS)]
            segments.append((res.bytes, color))

        if not segments:
            segments = [(1.0, '#2B2938')]

        number, unit = split_size(systeminfo.format_bytes(total))
        center = (f"<span size='large' weight='bold'>{number}</span>\n"
                  f"<span size='small'>{unit}</span>")
        self.cat_donut.set_segments(segments, center_markup=center)

    def _refresh_categories(self):
        cats = {c.key: c for c in self.categories}
        self._syncing = True
        for key, (check, size_lbl) in self.cat_rows.items():
            cat = cats[key]
            res = self.results.get(key)
            available = bool(res and res.available)

            check.set_sensitive(available)
            check.set_active(key in self.selected and available)

            if not available:
                size_lbl.set_text('Indisponível')
            elif res.files == 0 and res.bytes == 0:
                size_lbl.set_text('Vazio')
            else:
                size_lbl.set_text(systeminfo.format_bytes(res.bytes))
        self._syncing = False

    def _on_cat_toggle(self, check, key):
        if self._syncing:
            return
        if check.get_active():
            self.selected.add(key)
        else:
            self.selected.discard(key)

    def _sync_checks(self):
        self._syncing = True
        for key, (check, _size) in self.cat_rows.items():
            if check.get_sensitive():
                check.set_active(key in self.selected)
        self._syncing = False

    # ---- limpeza ----
    def _start_clean(self, keys):
        keys = {key for key in keys if key in self.results}
        if not keys:
            dialogs.show_info(self, 'Nada selecionado',
                              'Selecione ao menos uma categoria para limpar.')
            return
        if self._busy:
            return

        total = sum(self.results[key].bytes for key in keys)
        if total == 0:
            dialogs.show_info(self, 'Nada para limpar',
                              'Nenhum arquivo foi encontrado nas categorias '
                              'selecionadas.')
            return

        selected_cats = [cat for cat in self.categories if cat.key in keys]
        needs_home = any(not cat.requires_admin for cat in selected_cats)
        home = Path.home()
        if needs_home and not os.access(home, os.W_OK):
            dialogs.show_info(self, 'Sem permissão',
                              f'Não é possível gravar em {home}. '
                              'A limpeza foi cancelada.')
            return

        message = (f'Serão removidos {systeminfo.format_bytes(total)} em '
                   f'{plural(len(keys), "categoria", "categorias")}. '
                   'Esta ação não pode ser desfeita.')
        if 'browsers' in keys:
            message += ('\n\nFeche os navegadores para liberar mais espaço; '
                        'abertos, eles podem recriar o cache.')
        if any(cat.requires_admin for cat in selected_cats):
            message += ('\n\nSerá pedida a senha de administrador para '
                        'limpar o cache do APT.')

        def do_clean():
            self._run_clean(keys)

        if settings.load_settings().confirm_before_clean:
            dialogs.confirm(self, 'Confirmar limpeza', message, 'Limpar',
                            do_clean)
        else:
            do_clean()

    def _run_clean(self, keys):
        self._set_busy(True)
        self.status_text.set_text('Limpando...')
        threading.Thread(target=self._clean_worker, args=(set(keys),),
                         daemon=True).start()

    def _clean_worker(self, keys):
        try:
            report = scanner.clean_selected(keys, self.categories)
        except Exception as exc:  # pragma: no cover - falha inesperada
            GLib.idle_add(self._clean_failed, str(exc))
            return

        entry = history.HistoryEntry(
            timestamp=datetime.now().isoformat(timespec='seconds'),
            bytes=report.bytes,
            files=report.files,
            categories=tuple(sorted(keys)),
            errors=report.errors,
        )

        history_error = None
        if settings.load_settings().keep_history:
            try:
                history.append_entry(entry)
            except Exception as exc:  # histórico não pode desfazer a limpeza
                history_error = str(exc)

        errors = [res.error for res in report.per_category.values()
                  if res.error]
        GLib.idle_add(self._clean_done, report, history_error, errors)

    def _clean_failed(self, message):
        self.status_text.set_text('A limpeza não pôde ser concluída')
        self._set_busy(False)
        dialogs.show_info(self, 'Falha na limpeza',
                          f'Ocorreu um erro durante a limpeza:\n{message}')
        return False

    def _clean_done(self, report, history_error, errors=()):
        message = (f'{systeminfo.format_bytes(report.bytes)} liberados, '
                   f'{plural(report.files, "arquivo removido", "arquivos removidos")}.')
        if report.errors == 1:
            message += '\n1 item não pôde ser removido.'
        elif report.errors > 1:
            message += f'\n{report.errors} itens não puderam ser removidos.'
        for error in errors:
            message += f'\n\n{error}'
        if history_error:
            message += (f'\n\nAviso: não foi possível salvar o histórico '
                        f'({history_error}).')

        # Feedback imediato enquanto a nova varredura roda em segundo plano.
        remaining = max(0, self._recoverable_total() - report.bytes)
        self.recoverable_label.set_text(systeminfo.format_bytes(remaining))
        self.recoverable_sub.set_text('Atualizando após a limpeza...')

        dialogs.show_info(self, 'Limpeza concluída', message)
        self.status_text.set_text('Pronto para ajudar seu sistema!')
        self._set_busy(False)
        self._refresh_history()
        self._start_scan()
        return False

    def _set_busy(self, busy):
        self._busy = busy
        for btn in self.action_buttons:
            btn.set_sensitive(not busy)
        self.details_btn.set_sensitive(not busy)
        self.history_btn.set_sensitive(not busy)

    # ---- CPU ----
    def _tick_cpu(self):
        percent, self._cpu_sample = systeminfo.sample_cpu(self._cpu_sample)

        value, _pct = self.metric_labels['cpu']
        value.set_text(systeminfo.format_percent(percent))
        self.metric_bars['cpu'].set_fraction(percent / 100.0)

        self._line_values.append(percent / 100.0)
        self._line_values = self._line_values[-30:]
        self.line_chart.set_values(self._line_values)

        self._refresh_memory_panel()
        return True

    # ---- diálogos ----
    def _open_details(self):
        if self._busy:
            return
        dialog = dialogs.DetailsDialog(self, self.categories, self.results,
                                       self.selected, self._start_clean)
        dialog.connect('close-request', self._on_details_closed)
        dialog.present()

    def _on_details_closed(self, _dialog):
        self._sync_checks()
        return False

    def _open_history(self):
        dialog = dialogs.HistoryDialog(self, history.load_history(),
                                       self._clear_history)
        dialog.present()

    def _clear_history(self):
        history.clear_history()
        self._refresh_history()

    def _refresh_history(self):
        entries = history.load_history()

        child = self.history_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.history_list.remove(child)
            child = next_child

        self.history_rows = []
        recent = entries[-3:][::-1]
        if not recent:
            self.history_list.append(
                txt('Nenhuma limpeza registrada ainda', 'empty-text'))
            return

        for entry in recent:
            r = hbox(10)
            r.append(markup('<span foreground="#25CE60">✓</span>'))

            info = vbox(1)
            info.set_hexpand(True)
            info.append(txt('Limpeza realizada', 'op-title'))
            info.append(txt(f'Espaço liberado: '
                            f'{systeminfo.format_bytes(entry.bytes)} · '
                            f'{plural(entry.files, "arquivo", "arquivos")}',
                            'op-sub'))
            r.append(info)

            r.append(txt(history.format_timestamp(entry.timestamp), 'op-date'))
            self.history_list.append(r)
            self.history_rows.append(r)

    def _open_optimizer(self):
        dialog = dialogs.OptimizerDialog(self, on_done=self._start_scan)
        dialog.present()

    def _open_adjustments(self):
        dialog = dialogs.AdjustmentsDialog(self)
        dialog.present()

    def _show_settings(self):
        dialog = dialogs.SettingsDialog(self)
        dialog.present()

    def _show_help(self):
        dialogs.show_info(
            self, 'Ajuda',
            'Use "Limpeza Inteligente" para revisar as categorias e remover '
            'arquivos temporários com segurança.\n\n'
            'Nada fora da sua pasta pessoal e de /tmp é apagado, e as pastas '
            'raiz nunca são removidas.')

    def _show_about(self):
        dialogs.show_info(
            self, 'Sobre o Cleanix',
            'Cleanix 1.0\nLimpeza segura para Ubuntu, feita com GTK4.\n\n'
            'Seu sistema sempre em ótima forma.')
