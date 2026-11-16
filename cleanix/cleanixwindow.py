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

from . import (charts, dialogs, history, i18n, memory, scanner, settings,
              systeminfo)

CATEGORY_COLORS = ('#3295F5', '#20C957', '#F4510B', '#914CF5', '#F5A623')
HEALTH_TEXTS = {
    'ok': ('health.ok.title', '#25CE60', '✓', 'health.ok.message',
           'ok-text'),
    'warn': ('health.warn.title', '#F5A623', '!', 'health.warn.message',
             'warn-text'),
    'bad': ('health.bad.title', '#F4510B', '×', 'health.bad.message',
            'bad-text'),
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
        self._cpu_sample = None
        self._line_values = []
        self._memory_values = []
        self.cat_rows = {}
        self.history_rows = []
        self.metric_labels = {}
        self.metric_bars = {}

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
        names.append(txt(i18n.t('app.name'), 'app-name'))
        names.append(txt(i18n.t('app.subtitle'), 'app-sub'))
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
            (i18n.t('sidebar.home'), 'go-home-symbolic', True, None),
            (i18n.t('sidebar.cleanup'), 'edit-clear-symbolic', False,
             lambda *_: self._open_details()),
            (i18n.t('sidebar.optimize'),
             'utilities-system-monitor-symbolic', False,
             lambda *_: self._open_optimizer()),
            (i18n.t('sidebar.adjustments'), 'emblem-system-symbolic', False,
             lambda *_: self._open_adjustments()),
            (i18n.t('sidebar.xray'), 'computer-symbolic', False,
             lambda *_: self._open_xray()),
            (i18n.t('sidebar.space'), 'folder-symbolic', False,
             lambda *_: self._open_space_analysis()),
        ]
        for name, icon, active, on_click in items:
            side.append(self._side_item(name, icon, active, on_click))

        sep = Gtk.Separator()
        sep.add_css_class('side-sep')
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        side.append(sep)

        for name, icon, on_click in [
            (i18n.t('sidebar.history'), 'document-open-symbolic',
             lambda *_: self._open_history()),
            (i18n.t('sidebar.help_about'), 'help-about-symbolic',
             lambda *_: self._show_help_about()),
        ]:
            side.append(self._side_item(name, icon, False, on_click))

        expand = Gtk.Box()
        expand.set_vexpand(True)
        side.append(expand)

        name, version = systeminfo.distro_info()
        ubuntu = vbox(2)
        ubuntu.set_margin_top(8)
        ubuntu.set_halign(Gtk.Align.CENTER)
        ubuntu.append(emoji('⬤', 'ubuntu-logo'))
        ubuntu.append(txt(name, 'ubuntu-name', halign=Gtk.Align.CENTER))
        if version:
            ubuntu.append(txt(version, 'ubuntu-ver',
                              halign=Gtk.Align.CENTER))
        side.append(ubuntu)
        return side

    def _side_item(self, name, icon, active, on_click=None):
        btn = Gtk.Button()
        btn.add_css_class('side-item')
        if active:
            btn.add_css_class('side-active')

        row = hbox(12)
        row.append(sidebar_icon(icon))

        labels = vbox(0)
        labels.set_valign(Gtk.Align.CENTER)
        labels.append(txt(name, 'side-title'))
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
        content.append(self._block_cleanup())
        content.append(self._block_memory())
        content.append(self._block_disk_cpu())
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
        self.health_title = txt(i18n.t('health.ok.title'), 'h1')
        info.append(self.health_title)
        self.last_check_label = txt(i18n.t('health.not_checked'), 'sub')
        info.append(self.last_check_label)

        ok = hbox(6)
        self.health_icon = markup('<span foreground="#25CE60">✓</span>')
        ok.append(self.health_icon)
        self.health_text = txt(i18n.t('health.ok.message'), 'ok-text')
        ok.append(self.health_text)
        info.append(ok)

        geral.append(info)
        geral.set_hexpand(True)
        card.append(geral)

        card.append(vsep())
        card.append(self._metric('disk', '🗄️', i18n.t('metric.disk_free'),
                                 '#20C957'))
        card.append(vsep())
        card.append(self._metric('mem', '🟩', i18n.t('metric.memory'),
                                 '#3295F5'))
        card.append(vsep())
        card.append(self._metric('cpu', '🟪', i18n.t('metric.cpu'),
                                 '#914CF5'))
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
        head.append(txt(i18n.t('memory.title'), 'card-title'))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)

        self.memory_release_btn = Gtk.Button(
            label=i18n.t('memory.release'))
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
        self.memory_panel_sub = txt(i18n.t('memory.reading'), 'muted')
        info.append(self.memory_panel_sub)

        stats = hbox(16)
        stats.set_margin_top(4)
        self.memory_available_label = txt(i18n.t('memory.available', value='—'),
                                          'muted')
        self.memory_cache_label = txt(i18n.t('memory.cache', value='—'),
                                      'muted')
        stats.append(self.memory_available_label)
        stats.append(self.memory_cache_label)
        info.append(stats)
        body.append(info)

        chart_box = vbox(2)
        chart_box.set_hexpand(True)
        chart_box.set_valign(Gtk.Align.CENTER)
        self.memory_chart = charts.make_line_chart(
            width=320, height=96, color='#3295F5')
        self.memory_chart.set_values(self._memory_values)
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
            i18n.t('memory.of_total',
                   total=systeminfo.format_bytes(mem.total),
                   percent=i18n.format_number(mem.percent_used, 0)))
        self.memory_available_label.set_text(
            i18n.t('memory.available',
                   value=systeminfo.format_bytes(mem.available)))
        self.memory_cache_label.set_text(
            i18n.t('memory.cache', value=systeminfo.format_bytes(cache)))

        self._memory_values.append(mem.percent_used / 100.0)
        self._memory_values = self._memory_values[-30:]
        self.memory_chart.set_values(self._memory_values)

    def _open_memory(self):
        dialog = dialogs.MemoryDialog(
            self, on_released=self._refresh_memory_panel)
        dialog.present()

    # ---- Bloco 2: limpeza ----
    def _block_cleanup(self):
        card = vbox(10)
        card.add_css_class('card')

        head = hbox(8)
        head.append(emoji('🧹'))
        head.append(txt(i18n.t('cleanup.title'), 'card-title'))
        card.append(head)

        body = hbox(18)

        info = vbox(6)
        info.set_size_request(300, -1)
        info.set_valign(Gtk.Align.CENTER)
        info.append(txt(i18n.t('cleanup.recoverable'), 'metric-label'))
        self.recoverable_label = txt('—', 'big-number')
        info.append(self.recoverable_label)
        self.recoverable_sub = txt(i18n.t('cleanup.calculating'), 'muted',
                                   wrap=True)
        info.append(self.recoverable_sub)

        self.cleanup_review_btn = Gtk.Button(
            label=i18n.t('cleanup.review'))
        self.cleanup_review_btn.add_css_class('btn-green')
        self.cleanup_review_btn.set_margin_top(4)
        self.cleanup_review_btn.connect('clicked',
                                        lambda *_: self._open_details())
        info.append(self.cleanup_review_btn)
        body.append(info)

        self.cat_list = vbox(6)
        self.cat_list.set_hexpand(True)
        self.cat_list.set_valign(Gtk.Align.CENTER)
        for cat in self.categories:
            r = hbox(10)
            r.append(emoji(dialogs.CATEGORY_ICONS.get(cat.key, '📁')))
            name_lbl = txt(i18n.t(f'category.{cat.key}'), 'cat-name')
            name_lbl.set_hexpand(True)
            r.append(name_lbl)
            size_lbl = txt('—', 'cat-size')
            r.append(size_lbl)
            self.cat_rows[cat.key] = size_lbl
            self.cat_list.append(r)
        body.append(self.cat_list)

        self.cat_donut = charts.make_donut(
            [(1.0, '#2B2938')],
            center_markup="<span size='large' weight='bold'>—</span>",
            size=125, thickness=20)
        body.append(self.cat_donut)
        card.append(body)
        return card

    # ---- Bloco 3: disco e CPU ----
    def _block_disk_cpu(self):
        row = hbox(16)

        disk = vbox(10)
        disk.add_css_class('card')
        disk.set_hexpand(True)

        d_head = hbox(8)
        d_head.append(emoji('🥧'))
        d_head.append(txt(i18n.t('disk.title'), 'card-title'))
        disk.append(d_head)

        d_mid = hbox(16)
        self.disk_donut = charts.make_donut(
            [(0.5, '#3295F5'), (0.5, '#20C957')],
            center_markup="<span size='x-large' weight='bold'>—</span>",
            size=150, thickness=22)
        d_mid.append(self.disk_donut)

        legend = vbox(10)
        legend.set_valign(Gtk.Align.CENTER)
        l1 = hbox(8)
        l1.append(markup('<span foreground="#3295F5">●</span>'))
        self.disk_used_label = txt(i18n.t('disk.used', value='—'), 'legend')
        l1.append(self.disk_used_label)
        l2 = hbox(8)
        l2.append(markup('<span foreground="#20C957">●</span>'))
        self.disk_free_label = txt(i18n.t('disk.free', value='—'), 'legend')
        l2.append(self.disk_free_label)
        legend.append(l1)
        legend.append(l2)
        d_mid.append(legend)
        disk.append(d_mid)

        self.disk_total_label = txt(i18n.t('disk.total', value='—'), 'muted')
        disk.append(self.disk_total_label)

        disks_head = hbox(8)
        disks_head.set_margin_top(8)
        disks_head.append(txt(i18n.t('disks.section'), 'metric-label'))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        disks_head.append(spacer)
        self.disks_refresh_btn = Gtk.Button(label=i18n.t('disks.refresh'))
        self.disks_refresh_btn.add_css_class('status-btn')
        self.disks_refresh_btn.connect('clicked',
                                       lambda *_: self._refresh_disks_list())
        disks_head.append(self.disks_refresh_btn)
        disk.append(disks_head)

        self.disks_list = vbox(4)
        disk.append(self.disks_list)
        self._refresh_disks_list()
        row.append(disk)

        cpu = vbox(10)
        cpu.add_css_class('card')
        cpu.set_hexpand(True)

        c_head = hbox(8)
        c_head.append(emoji('📈'))
        c_head.append(txt(i18n.t('cpu.title'), 'card-title'))
        cpu.append(c_head)

        self.line_chart = charts.make_line_chart(width=180, height=120)
        self.line_chart.set_values(self._line_values)
        cpu.append(self.line_chart)

        cores = os.cpu_count() or 1
        self.cpu_now_label = txt(
            i18n.t('cpu.now', pct='—',
                   cores=i18n.tn('metric.cores', cores)), 'muted')
        cpu.append(self.cpu_now_label)
        row.append(cpu)
        return row

    # ---- Bloco 5: últimas ações ----
    def _block_bottom(self):
        b = vbox(10)
        b.add_css_class('card')

        head = hbox(8)
        head.append(emoji('🕘'))
        head.append(txt(i18n.t('history.title'), 'card-title'))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)
        self.history_btn = Gtk.Button(label=i18n.t('history.view'))
        self.history_btn.add_css_class('link-btn')
        self.history_btn.connect('clicked', lambda *_: self._open_history())
        head.append(self.history_btn)
        b.append(head)

        self.history_list = vbox(8)
        b.append(self.history_list)
        return b

    # ---- status bar ----
    def _status_bar(self):
        bar = hbox(10)
        bar.add_css_class('statusbar')

        bar.append(markup('<span foreground="#25CE60">✓</span>'))
        self.status_text = txt(i18n.t('status.ready'), 'status-text')
        bar.append(self.status_text)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        cfg = Gtk.Button()
        cfg.add_css_class('status-btn')
        cfg_c = hbox(6)
        cfg_c.append(emoji('⚙️'))
        cfg_c.append(txt(i18n.t('status.settings')))
        cfg.set_child(cfg_c)
        cfg.connect('clicked', lambda *_: self._show_settings())
        bar.append(cfg)
        return bar

    # ---- varredura ----
    def _start_scan(self):
        if self._busy:
            return False
        self._set_busy(True)
        self.status_text.set_text(i18n.t('status.scanning'))
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
        self.status_text.set_text(i18n.t('status.scan_failed'))
        self._set_busy(False)
        dialogs.show_info(self, i18n.t('scan.failed.title'),
                          i18n.t('scan.failed.body', detail=message))
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

        self.status_text.set_text(i18n.t('status.ready'))
        return False

    def _refresh_system(self):
        disk = systeminfo.get_disk_info('/')
        free_pct = 100.0 - disk.percent_used
        state = systeminfo.health_state(free_pct)
        self._set_health(state)

        if self.scan_time is not None:
            self.last_check_label.set_text(
                i18n.t('health.last_check',
                       time=f'{self.scan_time:%H:%M}'))

        total = disk.total or 1

        value, pct = self.metric_labels['disk']
        value.set_text(systeminfo.format_bytes(disk.free))
        pct.set_text(i18n.t('metric.free_pct',
                            pct=i18n.format_number(free_pct, 0)))
        self.metric_bars['disk'].set_fraction(disk.free / total)

        mem = systeminfo.get_mem_info()
        value, pct = self.metric_labels['mem']
        value.set_text(systeminfo.format_bytes(mem.used))
        pct.set_text(i18n.t('metric.used_pct',
                            pct=i18n.format_number(mem.percent_used, 0)))
        self.metric_bars['mem'].set_fraction(mem.percent_used / 100.0)
        self._refresh_memory_panel(mem)

        cores = os.cpu_count() or 1
        _, cpu_pct = self.metric_labels['cpu']
        cpu_pct.set_text(i18n.tn('metric.cores', cores))

        used_frac = disk.used / total
        free_frac = disk.free / total
        self.disk_donut.set_segments(
            [(used_frac, '#3295F5'), (free_frac, '#20C957')],
            center_markup=(f"<span size='x-large' weight='bold'>"
                           f"{disk.percent_used:.0f}%</span>"))
        self.disk_used_label.set_text(
            i18n.t('disk.used', value=systeminfo.format_bytes(disk.used)))
        self.disk_free_label.set_text(
            i18n.t('disk.free', value=systeminfo.format_bytes(disk.free)))
        self.disk_total_label.set_text(
            i18n.t('disk.total', value=systeminfo.format_bytes(disk.total)))

    def _set_health(self, state):
        title_key, color, glyph, message_key, cls = HEALTH_TEXTS[state]
        self.health_ring.set_state(state)
        self.health_title.set_text(i18n.t(title_key))
        self.health_icon.set_markup(f'<span foreground="{color}">{glyph}</span>')
        self.health_text.set_text(i18n.t(message_key))
        for name in ('ok-text', 'warn-text', 'bad-text'):
            self.health_text.remove_css_class(name)
        self.health_text.add_css_class(cls)

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
            self.recoverable_sub.set_text(i18n.t('cleanup.found'))
        else:
            self.recoverable_sub.set_text(i18n.t('cleanup.nothing_found'))
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
        for key, size_lbl in self.cat_rows.items():
            res = self.results.get(key)
            available = bool(res and res.available)

            if not available:
                size_lbl.set_text(i18n.t('cleanup.unavailable'))
            elif res.files == 0 and res.bytes == 0:
                size_lbl.set_text(i18n.t('cleanup.empty'))
            else:
                size_lbl.set_text(systeminfo.format_bytes(res.bytes))

    # ---- limpeza ----
    def _start_clean(self, keys):
        keys = {key for key in keys if key in self.results}
        if not keys:
            dialogs.show_info(self, i18n.t('clean.none.title'),
                              i18n.t('clean.none.body'))
            return
        if self._busy:
            return

        total = sum(self.results[key].bytes for key in keys)
        if total == 0:
            dialogs.show_info(self, i18n.t('clean.empty.title'),
                              i18n.t('clean.empty.body'))
            return

        selected_cats = [cat for cat in self.categories if cat.key in keys]
        needs_home = any(not cat.requires_admin for cat in selected_cats)
        home = Path.home()
        if needs_home and not os.access(home, os.W_OK):
            dialogs.show_info(self, i18n.t('clean.no_permission.title'),
                              i18n.t('clean.no_permission.body',
                                     path=str(home)))
            return

        message = i18n.t(
            'clean.confirm.body',
            size=systeminfo.format_bytes(total),
            count=len(keys),
            categories=i18n.tn('clean.categories', len(keys)))
        if 'browsers' in keys:
            message += '\n\n' + i18n.t('clean.confirm.browsers')
        if any(cat.requires_admin for cat in selected_cats):
            message += '\n\n' + i18n.t('clean.confirm.admin')

        def do_clean():
            self._run_clean(keys)

        if settings.load_settings().confirm_before_clean:
            dialogs.confirm(self, i18n.t('clean.confirm.title'), message,
                            i18n.t('clean.confirm.action'), do_clean)
        else:
            do_clean()

    def _run_clean(self, keys):
        self._set_busy(True)
        self.status_text.set_text(i18n.t('status.cleaning'))
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
        self.status_text.set_text(i18n.t('status.clean_failed'))
        self._set_busy(False)
        dialogs.show_info(self, i18n.t('clean.failed.title'),
                          i18n.t('clean.failed.body', detail=message))
        return False

    def _clean_done(self, report, history_error, errors=()):
        message = i18n.tn('clean.done.files', report.files,
                          size=systeminfo.format_bytes(report.bytes))
        if report.errors == 1:
            message += '\n' + i18n.t('clean.done.errors.one')
        elif report.errors > 1:
            message += '\n' + i18n.t('clean.done.errors.other',
                                     n=report.errors)
        for error in errors:
            message += f'\n\n{error}'
        if history_error:
            message += '\n\n' + i18n.t('clean.done.history_error',
                                       detail=history_error)

        # Feedback imediato enquanto a nova varredura roda em segundo plano.
        remaining = max(0, self._recoverable_total() - report.bytes)
        self.recoverable_label.set_text(systeminfo.format_bytes(remaining))
        self.recoverable_sub.set_text(i18n.t('cleanup.updating'))

        dialogs.show_info(self, i18n.t('clean.done.title'), message)
        self.status_text.set_text(i18n.t('status.ready'))
        self._set_busy(False)
        self._refresh_history()
        self._start_scan()
        return False

    def _set_busy(self, busy):
        self._busy = busy
        for btn in (self.cleanup_review_btn, self.memory_release_btn,
                    self.history_btn):
            btn.set_sensitive(not busy)
        if hasattr(self, 'disks_refresh_btn'):
            self.disks_refresh_btn.set_sensitive(not busy)

    def _refresh_disks_list(self):
        child = self.disks_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.disks_list.remove(child)
            child = next_child

        try:
            disks = systeminfo._scan_disks()
        except Exception:
            disks = []

        # Agrupa: cada disco físico seguido de suas partições
        phys = [d for d in disks if d.get('type') == 'disk' and (d.get('size_total') or 0) > 0
                and not (d.get('name') or '').startswith(('loop', 'zram', 'ram'))]
        parts = [d for d in disks if d.get('type') in ('part', 'lvm', 'crypt') and (d.get('size_total') or 0) > 0]
        ordered = []
        used_parts = set()
        for disk in phys:
            ordered.append(disk)
            for p in parts:
                if p.get('parent') == disk.get('name'):
                    ordered.append(p)
                    used_parts.add(id(p))
        for p in parts:
            if id(p) not in used_parts:
                ordered.append(p)

        shown = 0
        for info in ordered:
            name = info.get('name') or ''
            total = info.get('size_total') or 0
            if total <= 0:
                continue
            model = (info.get('model') or '').strip()
            mounted = info.get('mounted')
            mount = (info.get('mount_point') or '').strip()
            used = info.get('size_used') or 0
            free = info.get('size_free') or total
            pct = info.get('pct_used') or 0
            is_disk = info.get('type') == 'disk'

            row = hbox(8)
            if is_disk:
                label = f"💽 {name}" + (f" · {model}" if model and model != name else "")
            else:
                label = f"   └ {name}" + (f" ({mount})" if mount else "")
            left = txt(label, 'cat-name' if is_disk else 'muted')
            left.set_hexpand(True)
            left.set_wrap(True)
            row.append(left)

            if mounted and mount:
                detail = i18n.t('disks.mounted_row',
                    mount=mount, total=systeminfo.format_bytes(total),
                    used=systeminfo.format_bytes(used),
                    free=systeminfo.format_bytes(free),
                    pct=i18n.format_number(pct, 0))
            elif is_disk and info.get('has_mounted_parts'):
                detail = i18n.t('disks.disk_with_parts',
                    total=systeminfo.format_bytes(total),
                    used=systeminfo.format_bytes(used),
                    pct=i18n.format_number(pct, 0))
            else:
                detail = i18n.t('disks.unmounted_row',
                    total=systeminfo.format_bytes(total))
            # indicador simples de saúde por uso
            if is_disk or mounted:
                if pct >= 90:
                    detail = '⚠ ' + detail
                elif pct >= 80:
                    detail = '! ' + detail
            row.append(txt(detail, 'muted'))
            if is_disk:
                smart_btn = Gtk.Button(label=i18n.t('disks.smart_check'))
                smart_btn.add_css_class('status-btn')
                smart_btn.connect(
                    'clicked',
                    lambda _b, n=name, m=model: dialogs.SmartHealthDialog(
                        self, n, m).present())
                row.append(smart_btn)
            self.disks_list.append(row)
            shown += 1
            if shown >= 12:
                break

        if shown == 0:
            self.disks_list.append(
                txt(i18n.t('disks.none'), 'empty-text'))

    # ---- CPU ----
    def _tick_cpu(self):
        percent, self._cpu_sample = systeminfo.sample_cpu(self._cpu_sample)

        value, _pct = self.metric_labels['cpu']
        value.set_text(systeminfo.format_percent(percent))
        self.metric_bars['cpu'].set_fraction(percent / 100.0)

        cores = os.cpu_count() or 1
        self.cpu_now_label.set_text(
            i18n.t('cpu.now', pct=i18n.format_number(percent, 0),
                   cores=i18n.tn('metric.cores', cores)))

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
        dialog.present()

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
                txt(i18n.t('history.empty'), 'empty-text'))
            return

        for entry in recent:
            r = hbox(10)
            r.append(markup('<span foreground="#25CE60">✓</span>'))

            info = vbox(1)
            info.set_hexpand(True)
            info.append(txt(i18n.t('history.entry'), 'op-title'))
            info.append(txt(
                i18n.t('history.entry_sub',
                       size=systeminfo.format_bytes(entry.bytes),
                       files=i18n.tn('history.files', entry.files)),
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
        dialog = dialogs.SettingsDialog(
            self, on_language_changed=self._apply_language)
        dialog.present()

    def _apply_language(self, code):
        """Troca o idioma e reconstrói a interface sem reiniciar o app."""
        if code not in i18n.LANGUAGES:
            return
        if not i18n.set_language(code):
            return

        self.cat_rows = {}
        self.metric_labels = {}
        self.metric_bars = {}
        self.history_rows = []

        self._build_ui()

        if self.results:
            self._refresh_system()
            self._refresh_recoverable()
            self._refresh_categories()
        self._refresh_history()

    def _open_xray(self):
        dialogs.XRayDialog(self).present()

    def _open_space_analysis(self):
        dialogs.SpaceAnalysisDialog(self).present()

    def _show_help_about(self):
        title, body = dialogs.help_about_text()
        dialogs.show_info(self, title, body)
