#!/usr/bin/python3
"""Icône de zone de notification pour la télécommande Freebox Pop.

À lancer avec le Python du système (pas celui du venv) : il a besoin de GTK.
    sudo apt install python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-3.0 \\
        gir1.2-ayatanaappindicator3-0.1

Clic sur l'icône -> menu : ouvrir la télécommande (fenêtre native détourée),
version web, relancer le serveur, quitter.
Le serveur (app.py, dans le venv) est démarré automatiquement.
"""
import argparse
import fcntl
import os
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppIndicator  # noqa: E402
    except (ValueError, ImportError):
        AppIndicator = None

HERE = Path(__file__).resolve().parent
CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "freebox-remote"
)
VENV_PYTHON = HERE / ".venv" / "bin" / "python"
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"
BROWSERS = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
    "microsoft-edge",
)


def server_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def find_host(cli_host):
    if cli_host:
        return cli_host
    if os.environ.get("FREEBOX_PLAYER_IP"):
        return os.environ["FREEBOX_PLAYER_IP"]
    f = CONFIG_DIR / "host"
    if f.exists():
        return f.read_text().strip()
    return None


def launch_window():
    """Ouvre la télécommande dans une petite fenêtre sans barre d'onglets."""
    for name in BROWSERS:
        path = shutil.which(name)
        if path:
            subprocess.Popen(
                [path, f"--app={URL}", "--window-size=300,880"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    subprocess.Popen(["xdg-open", URL])


def error_dialog(message: str):
    d = Gtk.MessageDialog(
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text="Télécommande Freebox",
    )
    d.format_secondary_text(message)
    d.run()
    d.destroy()


class Tray:
    def __init__(self, host: str):
        self.host = host
        self.proc = None
        self._tries = 0
        self.window = None

        self.menu = Gtk.Menu()
        self.open_item = Gtk.MenuItem(label="Ouvrir la télécommande")
        self.open_item.connect("activate", self.open_remote)
        web_item = Gtk.MenuItem(label="Ouvrir la version web")
        web_item.connect("activate", lambda *_: launch_window())
        restart = Gtk.MenuItem(label="Relancer le serveur")
        restart.connect("activate", self.restart_server)
        quit_item = Gtk.MenuItem(label="Quitter")
        quit_item.connect("activate", self.quit)
        for item in (
            self.open_item,
            web_item,
            restart,
            Gtk.SeparatorMenuItem(),
            quit_item,
        ):
            self.menu.append(item)
        self.menu.show_all()

        print(
            "[tray] démarrage, backend :",
            AppIndicator.__name__ if AppIndicator is not None else "Gtk.StatusIcon",
            flush=True,
        )
        if AppIndicator is not None:
            self.indicator = AppIndicator.Indicator.new_with_path(
                "freebox-remote",
                "freebox-remote",
                AppIndicator.IndicatorCategory.APPLICATION_STATUS,
                str(HERE),
            )
            self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.indicator.set_menu(self.menu)
            self.indicator.set_secondary_activate_target(self.open_item)
        else:  # repli : Gtk.StatusIcon (clic gauche = ouvrir, clic droit = menu)
            self.icon = Gtk.StatusIcon.new_from_file(str(HERE / "freebox-remote.svg"))
            self.icon.set_tooltip_text("Télécommande Freebox")
            self.icon.connect("activate", self.open_remote)
            self.icon.connect(
                "popup-menu",
                lambda _i, button, time: self.menu.popup(
                    None, None, None, None, button, time
                ),
            )

        self.start_server()

    # --- serveur ---------------------------------------------------------
    def start_server(self):
        if server_running():
            return
        if not VENV_PYTHON.exists():
            error_dialog(f"Environnement Python introuvable : {VENV_PYTHON}")
            return
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(CONFIG_DIR / "server.log", "ab")
        self.proc = subprocess.Popen(
            [str(VENV_PYTHON), str(HERE / "app.py"), "--host", self.host],
            cwd=HERE,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    def stop_server(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def restart_server(self, *_):
        self.stop_server()
        GLib.timeout_add(500, lambda: (self.start_server(), False)[1])

    # --- fenêtre ---------------------------------------------------------
    def open_remote(self, *_):
        self.start_server()
        self._tries = 0
        GLib.timeout_add(250, self._open_when_ready)

    def _open_when_ready(self):
        self._tries += 1
        if server_running() or self._tries > 40:
            self.show_native()
            return False
        return True

    def show_native(self):
        """Fenêtre GTK détourée ; repli sur la version web si elle est indisponible."""
        if self.window is None:
            try:
                from remote_window import RemoteWindow

                self.window = RemoteWindow(URL, CONFIG_DIR)
            except Exception as err:  # noqa: BLE001  (cairo manquant, etc.)
                print("[tray] fenêtre native indisponible :", err, flush=True)
                launch_window()
                return
        self.window.show_remote()

    def reopen(self):
        """Appelé par SIGUSR1 quand une 2e instance demande l'ouverture."""
        self.open_remote()
        return True  # garde le gestionnaire de signal actif

    def quit(self, *_):
        if self.window is not None:
            self.window.save_position()
        self.stop_server()
        Gtk.main_quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="IP du Player Pop")
    args = parser.parse_args()

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Instance unique : le fichier verrou contient le PID de l'instance active.
    lock = os.fdopen(
        os.open(CONFIG_DIR / "tray.lock", os.O_RDWR | os.O_CREAT, 0o644), "r+"
    )
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Déjà lancé : on lui demande d'afficher la télécommande.
        try:
            lock.seek(0)
            os.kill(int(lock.read().strip()), signal.SIGUSR1)
        except (ValueError, OSError):
            launch_window()
        return
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()

    host = find_host(args.host)
    if not host:
        error_dialog(
            "IP du Player inconnue.\n"
            "Lance ./install.sh 192.168.1.NN ou écris l'IP dans "
            f"{CONFIG_DIR / 'host'}"
        )
        sys.exit(1)

    tray = Tray(host)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, tray.quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, tray.quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, tray.reopen)
    Gtk.main()


if __name__ == "__main__":
    main()
