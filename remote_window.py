"""Fenêtre GTK détourée de la télécommande Freebox Pop (sans navigateur).

Fenêtre sans cadre, fond transparent : seule la télécommande est visible.
Glisser sur le corps pour la déplacer, clic droit pour le menu.
Les commandes sont envoyées au serveur local (app.py) en HTTP.
"""
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from remote_art import HEIGHT, MARGIN, WIDTH, RemoteArt  # noqa: E402

KEYMAP = {
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "Return": "ok", "KP_Enter": "ok", "Escape": "back", "BackSpace": "back",
    "plus": "vol_up", "KP_Add": "vol_up", "equal": "vol_up",
    "minus": "vol_down", "KP_Subtract": "vol_down",
    "m": "mute", "M": "mute", "Page_Up": "ch_up", "Page_Down": "ch_down",
    "h": "home", "H": "home", "p": "power", "P": "power",
    "a": "assistant", "A": "assistant", "n": "netflix", "N": "netflix",
}
for _d in "0123456789":
    KEYMAP[_d] = f"n{_d}"
    KEYMAP[f"KP_{_d}"] = f"n{_d}"


def _load_scale(config_dir):
    raw = os.environ.get("FREEBOX_REMOTE_SCALE")
    f = config_dir / "scale"
    if raw is None and f.exists():
        raw = f.read_text().strip()
    try:
        return max(0.5, min(1.5, float(raw)))
    except (TypeError, ValueError):
        return 0.9


class RemoteWindow(Gtk.Window):
    def __init__(self, base_url, config_dir):
        super().__init__(title="Télécommande Freebox")
        self.base = base_url
        self.config_dir = config_dir
        self.art = RemoteArt()
        self.scale = _load_scale(config_dir)
        self._asked_pairing = False
        self._placed = False
        self._pos = None

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_app_paintable(True)
        self.set_role("freebox-remote")
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        css = Gtk.CssProvider()
        css.load_from_data(b"window.freebox-remote { background: transparent; box-shadow: none; }")
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.get_style_context().add_class("freebox-remote")
        try:
            self.set_icon_from_file(str(Path(__file__).resolve().parent / "freebox-remote.svg"))
        except Exception:  # pas de chargeur SVG : l'icône de fenêtre est facultative
            pass

        self.area = Gtk.DrawingArea()
        self.area.set_size_request(int(WIDTH * self.scale), int(HEIGHT * self.scale))
        self.area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.area.connect("draw", self.on_draw)
        self.area.connect("button-press-event", self.on_press)
        self.area.connect("button-release-event", self.on_release)
        self.area.connect("motion-notify-event", self.on_motion)
        self.area.connect("leave-notify-event", self.on_leave)
        self.add(self.area)

        self.connect("key-press-event", self.on_key)
        self.connect("delete-event", self.on_delete)
        self.connect("configure-event", self.on_configure)
        self.connect("hide", lambda *_: self.save_position())

        self.menu = Gtk.Menu()
        self.above_item = Gtk.CheckMenuItem(label="Toujours au premier plan")
        self.above_item.connect("toggled", lambda i: self.set_keep_above(i.get_active()))
        hide_item = Gtk.MenuItem(label="Masquer")
        hide_item.connect("activate", lambda *_: self.hide())
        for item in (self.above_item, hide_item):
            self.menu.append(item)
        self.menu.show_all()

        GLib.timeout_add_seconds(3, self._poll)

    # --- affichage ---------------------------------------------------------
    def show_remote(self):
        if not self._placed:
            self._placed = True
            pos = self._load_position()
            if pos:
                self.move(*pos)
            else:
                self.set_position(Gtk.WindowPosition.CENTER)
        self.show_all()
        self.present()
        self._poll()

    def on_draw(self, _area, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.scale(self.scale, self.scale)
        self.art.draw(cr)
        return False

    def on_delete(self, *_):
        self.hide()
        return True  # on garde la fenêtre : l'icône de notification reste active

    # --- position mémorisée -----------------------------------------------
    def on_configure(self, _w, event):
        self._pos = (event.x, event.y)
        return False

    def _load_position(self):
        try:
            d = json.loads((self.config_dir / "window.json").read_text())
            return int(d["x"]), int(d["y"])
        except Exception:
            return None

    def save_position(self):
        if self._pos is None:
            return
        try:
            (self.config_dir / "window.json").write_text(
                json.dumps({"x": int(self._pos[0]), "y": int(self._pos[1])})
            )
        except OSError:
            pass

    # --- souris ------------------------------------------------------------
    def _coords(self, event):
        return event.x / self.scale - MARGIN, event.y / self.scale - MARGIN

    def _set(self, hover=None, pressed="keep"):
        changed = False
        if hover != self.art.hover:
            self.art.hover, changed = hover, True
        if pressed != "keep" and pressed != self.art.pressed:
            self.art.pressed, changed = pressed, True
        if changed:
            self.area.queue_draw()

    def on_motion(self, _a, event):
        z = self.art.hit(*self._coords(event))
        self._set(hover=z.name if z else None)
        return True

    def on_leave(self, *_):
        self._set(hover=None)
        return True

    def on_press(self, _a, event):
        if event.button == 3:
            self.menu.popup_at_pointer(event)
            return True
        if event.button != 1:
            return False
        z = self.art.hit(*self._coords(event))
        if z:
            self._set(hover=z.name, pressed=z.name)
        else:  # corps de la télécommande : on déplace la fenêtre
            self.begin_move_drag(1, int(event.x_root), int(event.y_root), event.time)
        return True

    def on_release(self, _a, event):
        name = self.art.pressed
        z = self.art.hit(*self._coords(event))
        self._set(hover=z.name if z else None, pressed=None)
        if name and z and z.name == name:
            self.activate(z)
        return True

    # --- clavier -----------------------------------------------------------
    def on_key(self, _w, event):
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        name = KEYMAP.get(Gdk.keyval_name(event.keyval))
        if not name:
            return False
        z = next((z for z in self.art.zones if z.name == name), None)
        if z:
            self._flash(name)
            self.activate(z)
        return True

    def _flash(self, name):
        self._set(pressed=name)
        GLib.timeout_add(110, lambda: (self._set(pressed=None), False)[1])

    # --- commandes ---------------------------------------------------------
    def activate(self, zone):
        if zone.action == "key":
            self._post(f"/api/key/{zone.name}")
        elif zone.action == "app":
            self._post(f"/api/app/{zone.name}")
        elif zone.action == "led" and self.art.state != "connected":
            self.start_pairing()

    def _http(self, method, path, body=None):
        data = None
        if body is not None:
            data = json.dumps(body).encode()
        elif method == "POST":
            data = b""
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read() or b"{}")

    def _post(self, path):
        def run():
            try:
                self._http("POST", path)
            except Exception as err:
                print("[remote]", path, err, flush=True)

        threading.Thread(target=run, daemon=True).start()

    # --- état et appairage -------------------------------------------------
    def _poll(self):
        if self.get_visible():
            threading.Thread(target=self._fetch_state, daemon=True).start()
        return True

    def _fetch_state(self):
        try:
            state = self._http("GET", "/api/status")["state"]
        except Exception:
            state = "offline"
        GLib.idle_add(self._set_state, state)

    def _set_state(self, state):
        if state != self.art.state:
            self.art.state = state
            self.area.queue_draw()
        if state == "needs_pairing" and not self._asked_pairing:
            self._asked_pairing = True
            self.start_pairing()
        elif state == "connected":
            self._asked_pairing = False
        return False

    def start_pairing(self):
        def run():
            try:
                self._http("POST", "/api/pair/start")
            except Exception as err:
                print("[remote] appairage :", err, flush=True)
                return
            GLib.idle_add(self._pair_dialog)

        threading.Thread(target=run, daemon=True).start()

    def _pair_dialog(self):
        dlg = Gtk.Dialog(title="Appairer le Player Pop", transient_for=self, modal=True)
        dlg.add_button("Annuler", Gtk.ResponseType.CANCEL)
        dlg.add_button("Valider", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        label = Gtk.Label(label="Un code s'affiche sur la TV.\nSaisis-le pour autoriser cette télécommande.")
        entry = Gtk.Entry(max_length=6, width_chars=8, activates_default=True)
        entry.set_alignment(0.5)
        err = Gtk.Label(label="")
        for w in (label, entry, err):
            box.add(w)
        dlg.show_all()
        while dlg.run() == Gtk.ResponseType.OK:
            try:
                self._http("POST", "/api/pair/finish", {"code": entry.get_text()})
                break
            except urllib.error.HTTPError as e:
                err.set_text(e.read().decode(errors="replace") or "Code incorrect")
            except Exception as e:  # noqa: BLE001
                err.set_text(str(e))
        dlg.destroy()
        return False
