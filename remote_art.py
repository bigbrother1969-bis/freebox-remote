"""Dessin et zones cliquables de la télécommande Freebox Pop (cairo pur).

Aucune dépendance à GTK : ce module ne fait que dessiner sur un contexte cairo
et dire quel bouton se trouve sous un point. Coordonnées en « unités
télécommande » (le corps mesure 230 x 830), marge de 16 pour l'ombre portée.
"""
import math

import cairo

BODY_W, BODY_H = 230, 830
BODY_R = 52
MARGIN = 16
WIDTH, HEIGHT = BODY_W + 2 * MARGIN, BODY_H + 2 * MARGIN

TXT = (0.914, 0.925, 0.949)
RED = (0.898, 0.22, 0.231)
FREE_RED = (1.0, 0.353, 0.31)
COL = {
    "normal": (0.11, 0.125, 0.16),
    "hover": (0.153, 0.173, 0.22),
    "pressed": (0.196, 0.224, 0.278),
}
LED_CONNECTED = (0.298, 0.851, 0.392)
LED_OFFLINE = (0.333, 0.376, 0.478)
LED_WAIT = (1.0, 0.69, 0.125)

# --- géométrie (x, y, largeur, hauteur) ------------------------------------
RECTS = {
    "power": (146, 14, 62, 36),
    "netflix": (22, 62, 87, 38),
    "prime": (121, 62, 87, 38),
    "canal": (22, 112, 87, 38),
    "disney": (121, 112, 87, 38),
    "free": (22, 162, 186, 38),
    "assistant": (22, 212, 42, 34),
    "home": (146, 212, 62, 34),
    "back": (72, 449, 86, 36),
    "mute": (92, 540, 46, 34),
}
_NUM_W = (186 - 20) / 3
for _d in range(10):
    _col, _row = ((_d - 1) % 3, (_d - 1) // 3) if _d else (1, 3)
    RECTS[f"n{_d}"] = (22 + _col * (_NUM_W + 10), 633 + 44 * _row, _NUM_W, 34)

ROCKERS = {"vol": (22, 497, 50, 120), "ch": (158, 497, 50, 120)}
ROCKER_HALF = 38
DPAD = (115, 345, 92)
DIR_OFFSET = 62
DIR_R = 29
OK_R = 35
LED_POS = (58, 24)

APPS = {"netflix", "prime", "canal", "disney", "free"}


class Zone:
    def __init__(self, name, action, shape, geom):
        self.name, self.action, self.shape, self.geom = name, action, shape, geom

    def contains(self, x, y):
        if self.shape == "rect":
            gx, gy, gw, gh = self.geom
            return gx <= x <= gx + gw and gy <= y <= gy + gh
        cx, cy, r = self.geom
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _build_zones():
    zones = [Zone("led", "led", "circle", (*LED_POS, 8))]
    for name, rect in RECTS.items():
        zones.append(Zone(name, "app" if name in APPS else "key", "rect", rect))
    dx, dy, _ = DPAD
    zones.append(Zone("ok", "key", "circle", (dx, dy, OK_R)))
    for name, (ox, oy) in {
        "up": (0, -DIR_OFFSET),
        "down": (0, DIR_OFFSET),
        "left": (-DIR_OFFSET, 0),
        "right": (DIR_OFFSET, 0),
    }.items():
        zones.append(Zone(name, "key", "circle", (dx + ox, dy + oy, DIR_R)))
    for key, (x, y, w, h) in ROCKERS.items():
        up, down = ("vol_up", "vol_down") if key == "vol" else ("ch_up", "ch_down")
        zones.append(Zone(up, "key", "rect", (x, y, w, ROCKER_HALF)))
        zones.append(Zone(down, "key", "rect", (x, y + h - ROCKER_HALF, w, ROCKER_HALF)))
    return zones


# --- primitives de dessin ---------------------------------------------------
def rr(cr, x, y, w, h, r):
    """Chemin de rectangle arrondi."""
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def text(cr, s, cx, cy, size, color=TXT, bold=False, italic=False, family="Sans"):
    cr.select_font_face(
        family,
        cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
    )
    cr.set_font_size(size)
    e = cr.text_extents(s)  # (x_bearing, y_bearing, width, height, ...)
    cr.set_source_rgb(*color)
    cr.move_to(cx - e[0] - e[2] / 2, cy + size * 0.36)
    cr.show_text(s)


def icon(cr, name, cx, cy, size, color=TXT):
    """Pictogrammes dessinés sur une grille 24 x 24."""
    cr.save()
    cr.translate(cx - size / 2, cy - size / 2)
    cr.scale(size / 24.0, size / 24.0)
    cr.set_source_rgb(*color)
    cr.set_line_width(1.8)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if name == "power":
        cr.arc(12, 12.8, 7.6, math.radians(-48), math.radians(228))
        cr.stroke()
        cr.move_to(12, 3.5)
        cr.line_to(12, 11)
        cr.stroke()
    elif name == "home":
        cr.move_to(3.5, 19.5)
        cr.line_to(3.5, 10.3)
        cr.line_to(12, 4)
        cr.line_to(20.5, 10.3)
        cr.line_to(20.5, 19.5)
        cr.close_path()
        cr.stroke()
    elif name == "back":
        cr.move_to(9, 7)
        cr.line_to(4.5, 11.5)
        cr.line_to(9, 16)
        cr.stroke()
        cr.move_to(4.5, 11.5)
        cr.line_to(15, 11.5)
        cr.arc(15, 16, 4.5, -math.pi / 2, math.pi / 2)
        cr.line_to(12, 20.5)
        cr.stroke()
    elif name == "mute":
        cr.move_to(4, 9.5)
        cr.line_to(7.5, 9.5)
        cr.line_to(12, 6)
        cr.line_to(12, 18)
        cr.line_to(7.5, 14.5)
        cr.line_to(4, 14.5)
        cr.close_path()
        cr.stroke()
        cr.move_to(16, 9.5)
        cr.line_to(20.5, 14.5)
        cr.move_to(20.5, 9.5)
        cr.line_to(16, 14.5)
        cr.stroke()
    elif name == "assistant":
        for (x, y, r), rgb in (
            ((8, 8.5, 3.2), (0.259, 0.522, 0.957)),
            ((14.5, 7.5, 2.2), (0.918, 0.263, 0.208)),
            ((16.5, 13, 2.2), (0.984, 0.737, 0.02)),
            ((11, 16, 2.6), (0.204, 0.659, 0.325)),
        ):
            cr.set_source_rgb(*rgb)
            cr.arc(x, y, r, 0, 2 * math.pi)
            cr.fill()
    cr.restore()


def _sign(cr, kind, cx, cy, color=TXT):
    cr.set_source_rgb(*color)
    cr.set_line_width(1.6)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(cx - 6, cy)
    cr.line_to(cx + 6, cy)
    if kind == "+":
        cr.move_to(cx, cy - 6)
        cr.line_to(cx, cy + 6)
    cr.stroke()


APP_LABELS = {
    "netflix": ("NETFLIX", dict(size=12, bold=True, color=RED)),
    "prime": ("prime video", dict(size=11.5, bold=True)),
    "canal": ("CANAL+", dict(size=13, bold=True)),
    "disney": ("Disney+", dict(size=14)),
}


class RemoteArt:
    def __init__(self):
        self.hover = None
        self.pressed = None
        self.state = "offline"  # offline | needs_pairing | pairing | connected
        self.zones = _build_zones()

    def hit(self, x, y):
        for z in self.zones:
            if z.contains(x, y):
                return z
        return None

    def _st(self, name):
        if name == self.pressed:
            return "pressed"
        if name == self.hover:
            return "hover"
        return "normal"

    # --- éléments -----------------------------------------------------------
    def _pill(self, cr, name, rect=None):
        x, y, w, h = rect or RECTS[name]
        st = self._st(name)
        off = 1 if st == "pressed" else 0
        if st != "pressed":
            cr.set_source_rgba(0, 0, 0, 0.35)
            rr(cr, x, y + 2, w, h, h / 2)
            cr.fill()
        cr.set_source_rgb(*COL[st])
        rr(cr, x, y + off, w, h, h / 2)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.set_line_width(1)
        cr.stroke()
        return x + w / 2, y + h / 2 + off

    def _body(self, cr):
        for i in range(10, 0, -1):
            cr.set_source_rgba(0, 0, 0, 0.04)
            rr(cr, -i, 6 - i, BODY_W + 2 * i, BODY_H + 2 * i, BODY_R + i)
            cr.fill()
        g = cairo.LinearGradient(0, 0, 0, BODY_H)
        g.add_color_stop_rgb(0, 0.196, 0.22, 0.271)
        g.add_color_stop_rgb(1, 0.149, 0.165, 0.208)
        cr.set_source(g)
        rr(cr, 0, 0, BODY_W, BODY_H, BODY_R)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.set_line_width(1)
        cr.stroke()
        cr.set_source_rgba(1, 1, 1, 0.08)
        rr(cr, 1, 1, BODY_W - 2, BODY_H - 2, BODY_R - 1)
        cr.stroke()

    def _top(self, cr):
        cr.set_source_rgb(0.06, 0.067, 0.086)
        cr.arc(36, 24, 2.5, 0, 2 * math.pi)
        cr.fill()
        lx, ly = LED_POS
        if self.state == "connected":
            col = LED_CONNECTED
            cr.set_source_rgba(*col, 0.25)
            cr.arc(lx, ly, 6.5, 0, 2 * math.pi)
            cr.fill()
        else:
            col = LED_OFFLINE if self.state == "offline" else LED_WAIT
        cr.set_source_rgb(*col)
        cr.arc(lx, ly, 2.8, 0, 2 * math.pi)
        cr.fill()
        cx, cy = self._pill(cr, "power")
        icon(cr, "power", cx, cy, 20)

    def _apps(self, cr):
        for name, (label, kw) in APP_LABELS.items():
            cx, cy = self._pill(cr, name)
            text(cr, label, cx, cy, **kw)
        cx, cy = self._pill(cr, "free")
        text(cr, "free", cx, cy - 1, 26, color=FREE_RED, italic=True, family="Serif")

    def _assist_home(self, cr):
        cx, cy = self._pill(cr, "assistant")
        icon(cr, "assistant", cx, cy, 22)
        cx, cy = self._pill(cr, "home")
        icon(cr, "home", cx, cy, 24)

    def _dpad(self, cr):
        cx, cy, R = DPAD
        g = cairo.RadialGradient(cx, cy - 45, 6, cx, cy, R + 8)
        g.add_color_stop_rgb(0, 0.137, 0.157, 0.204)
        g.add_color_stop_rgb(1, 0.098, 0.11, 0.141)
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.arc(cx, cy + 2, R, 0, 2 * math.pi)
        cr.fill()
        cr.set_source(g)
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.set_line_width(1)
        cr.stroke()
        for name, (ox, oy) in {
            "up": (0, -DIR_OFFSET),
            "down": (0, DIR_OFFSET),
            "left": (-DIR_OFFSET, 0),
            "right": (DIR_OFFSET, 0),
        }.items():
            px, py = cx + ox, cy + oy
            st = self._st(name)
            if st != "normal":
                cr.set_source_rgba(1, 1, 1, 0.05 if st == "hover" else 0.11)
                cr.arc(px, py, DIR_R, 0, 2 * math.pi)
                cr.fill()
            cr.set_source_rgb(0.24, 0.27, 0.333)
            cr.arc(px, py, 2.5, 0, 2 * math.pi)
            cr.fill()
        st = self._st("ok")
        off = 1 if st == "pressed" else 0
        if st != "pressed":
            cr.set_source_rgba(0, 0, 0, 0.35)
            cr.arc(cx, cy + 2, OK_R, 0, 2 * math.pi)
            cr.fill()
        cr.set_source_rgb(*COL[st])
        cr.arc(cx, cy + off, OK_R, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.stroke()

    def _back(self, cr):
        cx, cy = self._pill(cr, "back")
        icon(cr, "back", cx, cy, 24)

    def _rocker(self, cr, key, up, down, label):
        x, y, w, h = ROCKERS[key]
        cr.set_source_rgba(0, 0, 0, 0.35)
        rr(cr, x, y + 2, w, h, w / 2)
        cr.fill()
        cr.set_source_rgb(*COL["normal"])
        rr(cr, x, y, w, h, w / 2)
        cr.fill()
        cr.save()
        rr(cr, x, y, w, h, w / 2)
        cr.clip()
        for name, zy in ((up, y), (down, y + h - ROCKER_HALF)):
            st = self._st(name)
            if st != "normal":
                cr.set_source_rgba(1, 1, 1, 0.05 if st == "hover" else 0.11)
                cr.rectangle(x, zy, w, ROCKER_HALF)
                cr.fill()
        cr.restore()
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.set_line_width(1)
        rr(cr, x, y, w, h, w / 2)
        cr.stroke()
        _sign(cr, "+", x + w / 2, y + 19)
        _sign(cr, "-", x + w / 2, y + h - 19)
        text(cr, label, x + w / 2, y + h / 2, 19)

    def _vp(self, cr):
        self._rocker(cr, "vol", "vol_up", "vol_down", "V")
        self._rocker(cr, "ch", "ch_up", "ch_down", "P")
        cx, cy = self._pill(cr, "mute")
        icon(cr, "mute", cx, cy, 22)

    def _numbers(self, cr):
        for d in range(10):
            cx, cy = self._pill(cr, f"n{d}")
            text(cr, str(d), cx, cy, 20)

    # --- point d'entrée -----------------------------------------------------
    def draw(self, cr):
        cr.save()
        cr.translate(MARGIN, MARGIN)
        self._body(cr)
        self._top(cr)
        self._apps(cr)
        self._assist_home(cr)
        self._dpad(cr)
        self._back(cr)
        self._vp(cr)
        self._numbers(cr)
        cr.restore()
