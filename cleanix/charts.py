#!/usr/bin/env python3
""" Custom Cairo-drawn widgets for the Cleanix interface. """

import math
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango


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


def make_bar(fraction, color_hex, width=170, height=14):
    """Rounded progress bar drawn with Cairo."""
    area = Gtk.DrawingArea()
    area.set_content_width(width)
    area.set_content_height(height)

    def draw(a, cr, w, h):
        r = h / 2.0
        rounded_rect(cr, 0, 0, w, h, r)
        cr.set_source_rgb(*hex_rgb('#393746'))
        cr.fill()

        fw = max(0.0, min(1.0, fraction)) * w
        if fw > 0.5:
            rounded_rect(cr, 0, 0, fw, h, min(r, fw / 2.0))
            cr.set_source_rgb(*hex_rgb(color_hex))
            cr.fill()

    area.set_draw_func(draw)
    return area


def make_health_ring(size=128):
    """Full green ring with a white check mark and a soft glow."""
    area = Gtk.DrawingArea()
    area.set_content_width(size)
    area.set_content_height(size)

    def draw(a, cr, w, h):
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) / 2.0 - 10

        # outer glow
        cr.set_source_rgba(*hex_rgb('#20C957'), 0.18)
        cr.set_line_width(14)
        cr.arc(cx, cy, r + 3, 0, 2 * math.pi)
        cr.stroke()

        # glowing ring
        cr.set_source_rgba(*hex_rgb('#25CE60'), 0.85)
        cr.set_line_width(10)
        cr.set_line_cap(1)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()

        # bright inner stroke
        cr.set_source_rgb(*hex_rgb('#3EF07A'))
        cr.set_line_width(4)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()

        # check mark
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(8)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        cr.move_to(cx - r * 0.42, cy + r * 0.02)
        cr.line_to(cx - r * 0.12, cy + r * 0.34)
        cr.line_to(cx + r * 0.46, cy - r * 0.32)
        cr.stroke()

    area.set_draw_func(draw)
    return area


def make_donut(segments, center_markup='', size=150, thickness=22,
               center_color='#F4F3FA'):
    """Donut chart from a list of (fraction, hexcolor). Returns a Gtk.Overlay
    so crisp Pango text can be centered on top."""
    drawing = Gtk.DrawingArea()
    drawing.set_content_width(size)
    drawing.set_content_height(size)

    def draw(a, cr, w, h):
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) / 2.0 - thickness / 2.0 - 3

        # subtle background circle
        cr.set_source_rgb(*hex_rgb('#2B2938'))
        cr.arc(cx, cy, r + thickness / 2.0, 0, 2 * math.pi)
        cr.fill()

        start = -math.pi / 2.0
        total = sum(v for v, _ in segments) or 1.0
        for val, color in segments:
            ang = (val / total) * 2 * math.pi
            if ang <= 0:
                continue
            cr.set_source_rgb(*hex_rgb(color))
            cr.set_line_width(thickness)
            cr.set_line_cap(0)
            cr.arc(cx, cy, r, start, start + ang)
            cr.stroke()
            start += ang

    drawing.set_draw_func(draw)

    overlay = Gtk.Overlay()
    overlay.set_child(drawing)
    overlay.set_size_request(size, size)

    if center_markup:
        lbl = Gtk.Label()
        lbl.set_markup(center_markup)
        lbl.set_halign(Gtk.Align.CENTER)
        lbl.set_valign(Gtk.Align.CENTER)
        lbl.set_justify(Gtk.Justification.CENTER)
        overlay.add_overlay(lbl)
    return overlay


def make_line_chart(width=340, height=110, color='#20C957'):
    """Rising irregular line chart with translucent area fill and faint grid."""
    area = Gtk.DrawingArea()
    area.set_content_width(width)
    area.set_content_height(height)
    area.set_hexpand(True)

    pts = [0.12, 0.30, 0.24, 0.38, 0.52, 0.44, 0.60, 0.55, 0.70, 0.63,
           0.78, 0.73, 0.86, 0.82, 0.95]

    def draw(a, cr, w, h):
        pad = 6
        # grid
        cr.set_source_rgba(*hex_rgb('#484555'), 0.55)
        cr.set_line_width(1)
        for i in range(1, 4):
            y = pad + (h - 2 * pad) * i / 4.0
            cr.move_to(pad, y)
            cr.line_to(w - pad, y)
            cr.stroke()

        n = len(pts)
        xs = [pad + (w - 2 * pad) * i / (n - 1) for i in range(n)]
        ys = [h - pad - p * (h - 2 * pad) for p in pts]

        # area fill
        cr.move_to(xs[0], h - pad)
        for x, y in zip(xs, ys):
            cr.line_to(x, y)
        cr.line_to(xs[-1], h - pad)
        cr.close_path()
        cr.set_source_rgba(*hex_rgb(color), 0.18)
        cr.fill()

        # bright line
        cr.set_source_rgb(*hex_rgb(color))
        cr.set_line_width(2.4)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        cr.move_to(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:]):
            cr.line_to(x, y)
        cr.stroke()

    area.set_draw_func(draw)
    return area


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

        # body
        cr.set_source_rgb(*hex_rgb('#8E7CC3'))
        rounded_rect(cr, x0, body_top, body_w, body_bot - body_top, 8)
        cr.fill()

        # lid
        cr.set_source_rgb(*hex_rgb('#B39DDB'))
        rounded_rect(cr, x0 - 5, h * 0.22, body_w + 10, h * 0.09, 4)
        cr.fill()

        # handle
        cr.set_source_rgb(*hex_rgb('#B39DDB'))
        rounded_rect(cr, cx - body_w * 0.18, h * 0.15, body_w * 0.36, h * 0.08, 3)
        cr.fill()

        # recycling arrows (three small triangles)
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
