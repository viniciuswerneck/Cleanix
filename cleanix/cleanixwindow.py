#!/usr/bin/env python3
""" Main window for Cleanix, faithful to the design mockup. """

from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Pango

from . import charts


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


class CleanixWindow(Gtk.ApplicationWindow):

    def __init__(self, application):
        super().__init__(application=application)
        self.set_title('Cleanix')
        self.set_decorated(False)          # custom title bar
        self._setup_css()
        self._build_ui()
        self._fit_to_screen()

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
            ('Início', 'go-home-symbolic', '', True),
            ('Cleaner', 'edit-clear-symbolic', '(Limpeza)', False),
            ('Optimizer', 'utilities-system-monitor-symbolic', '(Otimização)', False),
            ('Adjustments', 'emblem-system-symbolic', '(Ajustes)', False),
        ]
        for name, icon, sub, active in items:
            side.append(self._side_item(name, icon, sub, active))

        sep = Gtk.Separator()
        sep.add_css_class('side-sep')
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        side.append(sep)

        for name, icon, sub, active in [
            ('Histórico', 'document-open-symbolic', '', False),
            ('Sobre', 'help-about-symbolic', '', False),
        ]:
            side.append(self._side_item(name, icon, sub, active))

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

    def _side_item(self, name, icon, sub, active):
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
        content.append(self._block_cards())
        content.append(self._block_actions())
        content.append(self._block_bottom())
        return scroller

    # ---- Bloco 1: saúde ----
    def _block_health(self):
        card = hbox(16)
        card.add_css_class('card')

        # estado geral
        geral = hbox(18)
        geral.append(charts.make_health_ring(128))
        info = vbox(4)
        info.set_valign(Gtk.Align.CENTER)
        info.append(txt('Seu sistema está saudável!', 'h1'))
        info.append(txt('Última verificação: hoje às 10:24', 'sub'))
        ok = hbox(6)
        ok.append(markup('<span foreground="#25CE60">✓</span>'))
        ok.append(txt('Nenhum problema crítico encontrado.', 'ok-text'))
        info.append(ok)
        geral.append(info)
        geral.set_hexpand(True)
        card.append(geral)

        card.append(vsep())

        card.append(self._metric('🗄️', 'Disco Livre', '78,4 GB', '(46%)',
                                 '#20C957', 0.784))
        card.append(vsep())
        card.append(self._metric('🟩', 'Memória', '3,1 GB', '(37%)',
                                 '#3295F5', 0.37))
        card.append(vsep())
        card.append(self._metric('🟪', 'CPU', '2%', '(1 núcleo)',
                                 '#914CF5', 0.02))
        return card

    def _metric(self, icon, label, value, pct, color, fraction):
        box = vbox(4)
        box.set_size_request(120, -1)

        head = hbox(8)
        head.append(emoji(icon))
        head.append(txt(label, 'metric-label'))
        box.append(head)

        box.append(txt(value, 'metric-value'))
        box.append(txt(pct, 'metric-pct'))
        bar = charts.make_bar(fraction, color, width=140, height=14)
        bar.set_margin_top(4)
        box.append(bar)
        return box

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
        a_info.append(txt('2,48 GB', 'big-number'))
        a_info.append(txt('Arquivos desnecessários encontrados', 'muted'))
        a_top.append(a_info)
        a.append(a_top)

        btn = Gtk.Button()
        btn.add_css_class('btn-green')
        bcontent = hbox(8)
        bcontent.set_halign(Gtk.Align.CENTER)
        bcontent.append(emoji('🔍'))
        bcontent.append(txt('Ver Detalhes...', halign=Gtk.Align.CENTER))
        btn.set_child(bcontent)
        a.append(btn)
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
        donut = charts.make_donut(
            [(0.46, '#3295F5'), (0.54, '#20C957')],
            center_markup="<span size='x-large' weight='bold'>46%</span>",
            size=150, thickness=22)
        b_mid.append(donut)

        legend = vbox(10)
        legend.set_valign(Gtk.Align.CENTER)
        l1 = hbox(8)
        l1.append(markup('<span foreground="#3295F5">●</span>'))
        l1.append(txt('Usado   78,4 GB', 'legend'))
        l2 = hbox(8)
        l2.append(markup('<span foreground="#20C957">●</span>'))
        l2.append(txt('Livre   91,6 GB', 'legend'))
        legend.append(l1)
        legend.append(l2)
        b_mid.append(legend)
        b.append(b_mid)

        b.append(txt('Total: 170 GB', 'muted'))
        row.append(b)

        # ---- Cartão C: Sistema ----
        c = vbox(10)
        c.add_css_class('card')
        c.set_hexpand(True)

        c_head = hbox(8)
        c_head.append(emoji('📈'))
        c_head.append(txt('Sistema', 'card-title'))
        c.append(c_head)

        c.append(charts.make_line_chart(width=180, height=120))

        strip = hbox(8)
        strip.add_css_class('sys-strip')
        strip.append(markup('<span foreground="#25CE60">✓</span>'))
        strip.append(txt('Tudo funcionando bem!', 'ok-text'))
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
        row.append(self._action('🧹', 'Limpeza Inteligente',
                                'Remova arquivos temporários, caches e lixo do sistema.',
                                selected=True))
        row.append(self._action('🚀', 'Otimização',
                                'Melhore o desempenho do seu Ubuntu.'))
        row.append(self._action('🎛️', 'Ajustes',
                                'Personalize e ajuste seu sistema com segurança.'))
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
        listbox = vbox(8)
        listbox.set_hexpand(True)

        cats = [
            ('🗑️', 'Lixeira do Sistema', '567 MB'),
            ('📦', 'Cache do APT', '324 MB'),
            ('🖼️', 'Miniaturas de Imagens', '228 MB'),
            ('🌐', 'Cache dos Navegadores', '1,02 GB'),
            ('🗂️', 'Arquivos Temporários', '340 MB'),
        ]
        for icon, name, size in cats:
            r = hbox(10)
            r.append(markup('<span foreground="#3295F5">☑</span>'))
            r.append(emoji(icon))
            r.append(txt(name, 'cat-name'))
            name_lbl = r.get_last_child()
            name_lbl.set_hexpand(True)
            r.append(txt(size, 'cat-size'))
            listbox.append(r)
        inner.append(listbox)

        inner.append(charts.make_donut(
            [(0.45, '#3295F5'), (0.25, '#20C957'),
             (0.15, '#F4510B'), (0.15, '#914CF5')],
            center_markup="<span size='large' weight='bold'>2,48</span>\n"
                          "<span size='small'>GB</span>",
            size=125, thickness=20))
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
        head.append(markup('<span foreground="#3295F5">Ver Histórico →</span>'))
        b.append(head)

        ops = [
            ('Limpeza realizada com sucesso', 'Espaço liberado: 1,87 GB', 'Hoje, 10:20'),
            ('Otimização do sistema', 'Serviços ajustados: 3', 'Ontem, 21:15'),
            ('Limpeza realizada com sucesso', 'Espaço liberado: 952 MB', '05/11/2026'),
        ]
        for title, sub, date in ops:
            r = hbox(10)
            r.append(markup('<span foreground="#25CE60">✓</span>'))
            info = vbox(1)
            info.set_hexpand(True)
            info.append(txt(title, 'op-title'))
            info.append(txt(sub, 'op-sub'))
            r.append(info)
            r.append(txt(date, 'op-date'))
            b.append(r)
        row.append(b)
        return row

    # ---- status bar ----
    def _status_bar(self):
        bar = hbox(10)
        bar.add_css_class('statusbar')

        bar.append(markup('<span foreground="#25CE60">✓</span>'))
        bar.append(txt('Pronto para ajudar seu sistema!', 'status-text'))

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        cfg = Gtk.Button()
        cfg.add_css_class('status-btn')
        cfg_c = hbox(6)
        cfg_c.append(emoji('⚙️'))
        cfg_c.append(txt('Configurações'))
        cfg.set_child(cfg_c)
        bar.append(cfg)

        help_b = Gtk.Button()
        help_b.add_css_class('status-btn')
        help_c = hbox(6)
        help_c.append(emoji('❓'))
        help_c.append(txt('Ajuda'))
        help_b.set_child(help_c)
        bar.append(help_b)
        return bar
