#!/usr/bin/env python3
"""Widgets desenhados em Cairo, atualizáveis em tempo real."""

import math

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

RING_PALETTES = {
    'ok': ('#20C957', '#25CE60', '#3EF07A'),
    'warn': ('#F5A623', '#F5A623', '#FFC65C'),
    'bad': ('#F4510B', '#F4510B', '#FF7A18'),
}

DEFAULT_LINE_POINTS = [0.12, 0.30, 0.24, 0.38, 0.52, 0.44, 0.60, 0.55,
                       0.70, 0.63, 0.78, 0.73, 0.86, 0.82, 0.95]


def hex_rgb(h):
    """Convert '#RRGGBB' to an (r, g, b) tuple in 0..1."""
    h = h.lstrip('#')
    return (int(h[0:2], 16) / 255.0,
            int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0)


def rounded_rect(cr, x, y, w, h, r):
    """Build a rounded rectangle path in Cairo."""
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class ProgressBar(Gtk.DrawingArea):
    """Barra de progresso arredondada, atualizável."""

    def __init__(self, fraction=0.0, color='#20C957', width=170, height=14):
        super().__init__()
        self._fraction = fraction
        self._color = color
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_draw_func(self._draw)

    def set_fraction(self, fraction):
        self._fraction = max(0.0, min(1.0, fraction))
        self.queue_draw()

    def set_color(self, color):
        self._color = color
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        radius = h / 2.0
        rounded_rect(cr, 0, 0, w, h, radius)
        cr.set_source_rgb(*hex_rgb('#393746'))
        cr.fill()

        filled = max(0.0, min(1.0, self._fraction)) * w
        if filled > 0.5:
            rounded_rect(cr, 0, 0, filled, h, min(radius, filled / 2.0))
            cr.set_source_rgb(*hex_rgb(self._color))
            cr.fill()


class HealthRing(Gtk.DrawingArea):
    """Anel de saúde com brilho e glifo (check, exclamação ou X)."""

    def __init__(self, size=128):
        super().__init__()
        self._state = 'ok'
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_draw_func(self._draw)

    def set_state(self, state):
        self._state = state if state in RING_PALETTES else 'ok'
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) / 2.0 - 10
        glow, ring, bright = RING_PALETTES[self._state]

        cr.set_source_rgba(*hex_rgb(glow), 0.18)
        cr.set_line_width(14)
        cr.arc(cx, cy, radius + 3, 0, 2 * math.pi)
        cr.stroke()

        cr.set_source_rgba(*hex_rgb(ring), 0.85)
        cr.set_line_width(10)
        cr.set_line_cap(1)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        cr.set_source_rgb(*hex_rgb(bright))
        cr.set_line_width(4)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(8)
        cr.set_line_cap(1)
        cr.set_line_join(1)

        if self._state == 'ok':
            cr.move_to(cx - radius * 0.42, cy + radius * 0.02)
            cr.line_to(cx - radius * 0.12, cy + radius * 0.34)
            cr.line_to(cx + radius * 0.46, cy - radius * 0.32)
            cr.stroke()
        elif self._state == 'warn':
            cr.move_to(cx, cy - radius * 0.34)
            cr.line_to(cx, cy + radius * 0.12)
            cr.stroke()
            cr.arc(cx, cy + radius * 0.34, 5, 0, 2 * math.pi)
            cr.fill()
        else:
            cr.move_to(cx - radius * 0.28, cy - radius * 0.28)
            cr.line_to(cx + radius * 0.28, cy + radius * 0.28)
            cr.move_to(cx + radius * 0.28, cy - radius * 0.28)
            cr.line_to(cx - radius * 0.28, cy + radius * 0.28)
            cr.stroke()


class DonutChart(Gtk.Overlay):
    """Rosca com segmentos coloridos e texto Pango centralizado."""

    def __init__(self, segments, center_markup='', size=150, thickness=22,
                 center_color='#F4F3FA'):
        super().__init__()
        self._segments = list(segments)
        self._thickness = thickness

        self._drawing = Gtk.DrawingArea()
        self._drawing.set_content_width(size)
        self._drawing.set_content_height(size)
        self._drawing.set_draw_func(self._draw)
        self.set_child(self._drawing)
        self.set_size_request(size, size)

        self._label = Gtk.Label()
        self._label.set_halign(Gtk.Align.CENTER)
        self._label.set_valign(Gtk.Align.CENTER)
        self._label.set_justify(Gtk.Justification.CENTER)
        self.add_overlay(self._label)
        self.set_center_markup(center_markup)

    def set_segments(self, segments, center_markup=None):
        self._segments = list(segments)
        if center_markup is not None:
            self.set_center_markup(center_markup)
        self._drawing.queue_draw()

    def set_center_markup(self, markup):
        self._label.set_markup(markup or '')

    def _draw(self, area, cr, w, h):
        cx, cy = w / 2.0, h / 2.0
        thickness = self._thickness
        radius = min(w, h) / 2.0 - thickness / 2.0 - 3

        cr.set_source_rgb(*hex_rgb('#2B2938'))
        cr.arc(cx, cy, radius + thickness / 2.0, 0, 2 * math.pi)
        cr.fill()

        start = -math.pi / 2.0
        total = sum(value for value, _ in self._segments) or 1.0
        for value, color in self._segments:
            angle = (value / total) * 2 * math.pi
            if angle <= 0:
                continue
            cr.set_source_rgb(*hex_rgb(color))
            cr.set_line_width(thickness)
            cr.set_line_cap(0)
            cr.arc(cx, cy, radius, start, start + angle)
            cr.stroke()
            start += angle


class LineChart(Gtk.DrawingArea):
    """Gráfico de linha com área translúcida e grade discreta."""

    def __init__(self, width=340, height=110, color='#20C957'):
        super().__init__()
        self._values = list(DEFAULT_LINE_POINTS)
        self._color = color
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def set_values(self, values):
        self._values = [max(0.0, min(1.0, float(v))) for v in values]
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        pad = 6
        values = self._values
        real_data = len(values) >= 2
        if not real_data:
            values = [0.5, 0.5]

        cr.set_source_rgba(*hex_rgb('#484555'), 0.55)
        cr.set_line_width(1)
        for i in range(1, 4):
            y = pad + (h - 2 * pad) * i / 4.0
            cr.move_to(pad, y)
            cr.line_to(w - pad, y)
            cr.stroke()

        count = len(values)
        xs = [pad + (w - 2 * pad) * i / (count - 1) for i in range(count)]
        ys = [h - pad - value * (h - 2 * pad) for value in values]

        if real_data:
            cr.move_to(xs[0], h - pad)
            for x, y in zip(xs, ys):
                cr.line_to(x, y)
            cr.line_to(xs[-1], h - pad)
            cr.close_path()
            cr.set_source_rgba(*hex_rgb(self._color), 0.18)
            cr.fill()

        cr.set_source_rgb(*hex_rgb(self._color))
        cr.set_line_width(2.4)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        cr.move_to(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:]):
            cr.line_to(x, y)
        cr.stroke()


def make_bar(fraction=0.0, color_hex='#20C957', width=170, height=14):
    return ProgressBar(fraction=fraction, color=color_hex,
                       width=width, height=height)


def make_health_ring(size=128):
    return HealthRing(size=size)


def make_donut(segments, center_markup='', size=150, thickness=22,
               center_color='#F4F3FA'):
    return DonutChart(segments, center_markup=center_markup, size=size,
                      thickness=thickness, center_color=center_color)


def make_line_chart(width=340, height=110, color='#20C957'):
    return LineChart(width=width, height=height, color=color)


def make_trash_illustration(size=92):
    """Simple lilac trash can with a recycling symbol, drawn with Cairo."""
    area = Gtk.DrawingArea()
    area.set_content_width(size)
    area.set_content_height(size)

    def draw(a, cr, w, h):
        cx = w / 2.0
        body_top = h * 0.28
        body_bot = h * 0.9
        body_w = w * 0.5
        x0 = cx - body_w / 2.0

        cr.set_source_rgb(*hex_rgb('#8E7CC3'))
        rounded_rect(cr, x0, body_top, body_w, body_bot - body_top, 8)
        cr.fill()

        cr.set_source_rgb(*hex_rgb('#B39DDB'))
        rounded_rect(cr, x0 - 5, h * 0.22, body_w + 10, h * 0.09, 4)
        cr.fill()

        cr.set_source_rgb(*hex_rgb('#B39DDB'))
        rounded_rect(cr, cx - body_w * 0.18, h * 0.15,
                     body_w * 0.36, h * 0.08, 3)
        cr.fill()

        cr.set_source_rgb(*hex_rgb('#3EA55A'))
        for k in range(3):
            ang = -math.pi / 2 + k * (2 * math.pi / 3)
            ax = cx + math.cos(ang) * body_w * 0.18
            ay = (body_top + body_bot) / 2 + math.sin(ang) * body_w * 0.18
            cr.save()
            cr.translate(ax, ay)
            cr.rotate(ang + math.pi / 2)
            cr.move_to(0, -5)
            cr.line_to(4.5, 3)
            cr.line_to(-4.5, 3)
            cr.close_path()
            cr.fill()
            cr.restore()

    area.set_draw_func(draw)
    return area
