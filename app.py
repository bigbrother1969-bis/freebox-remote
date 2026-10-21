#!/usr/bin/env python3
"""Télécommande Freebox Pop (Player Pop / Android TV) – serveur local.

Usage :
    python app.py --host 192.168.1.XX
puis ouvrir http://127.0.0.1:8765
"""
import argparse
import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web
from androidtvremote2 import (
    AndroidTVRemote,
    CannotConnect,
    ConnectionClosed,
    InvalidAuth,
)

LOG = logging.getLogger("freebox-remote")

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "freebox-remote"
)
HERE = Path(__file__).resolve().parent

# Nom de touche côté interface -> code Android TV
KEYS = {
    "power": "POWER",
    "assistant": "ASSIST",
    "home": "HOME",
    "up": "DPAD_UP",
    "down": "DPAD_DOWN",
    "left": "DPAD_LEFT",
    "right": "DPAD_RIGHT",
    "ok": "DPAD_CENTER",
    "back": "BACK",
    "vol_up": "VOLUME_UP",
    "vol_down": "VOLUME_DOWN",
    "mute": "VOLUME_MUTE",
    "ch_up": "CHANNEL_UP",
    "ch_down": "CHANNEL_DOWN",
    **{f"n{i}": str(i) for i in range(10)},
}

# Boutons d'applis -> lien de lancement (modifiable ici).
APPS = {
    "netflix": "https://www.netflix.com/",
    "prime": "https://www.primevideo.com/",
    "canal": "https://www.canalplus.com/",
    "disney": "https://www.disneyplus.com/",
    # Le bouton « free » n'a pas de lien universel connu : à adapter.
    "free": "market://launch?id=fr.freebox.tv",
}


class Player:
    def __init__(self, host: str):
        self.host = host
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.remote = None  # créé dans la boucle asyncio (voir _ensure_remote)
        self.state = "offline"  # offline | needs_pairing | pairing | connected

    def _ensure_remote(self):
        # AndroidTVRemote exige une boucle asyncio déjà en cours d'exécution.
        if self.remote is None:
            self.remote = AndroidTVRemote(
                "freebox-remote-linux",  # ASCII obligatoire (nom DNS du certificat)
                str(CONFIG_DIR / "cert.pem"),
                str(CONFIG_DIR / "key.pem"),
                self.host,
            )

    async def connect(self):
        self._ensure_remote()
        await self.remote.async_generate_cert_if_missing()
        try:
            await self.remote.async_connect()
        except InvalidAuth:
            self.state = "needs_pairing"
            return
        except (CannotConnect, ConnectionClosed, OSError) as err:
            LOG.warning("Connexion impossible : %s", err)
            self.state = "offline"
            return
        self.state = "connected"
        self.remote.keep_reconnecting()
        LOG.info("Connecté au Player %s", self.host)

    async def retry_loop(self):
        while True:
            await asyncio.sleep(5)
            if self.state == "offline":
                await self.connect()

    async def start_pairing(self):
        self._ensure_remote()
        await self.remote.async_generate_cert_if_missing()
        await self.remote.async_start_pairing()
        self.state = "pairing"

    async def finish_pairing(self, code: str):
        await self.remote.async_finish_pairing(code.strip())
        await self.connect()


def build_app(player: Player) -> web.Application:
    async def index(_):
        return web.FileResponse(HERE / "index.html")

    async def status(_):
        return web.json_response({"state": player.state})

    async def key(request):
        name = request.match_info["name"]
        code = KEYS.get(name)
        if code is None:
            raise web.HTTPNotFound(text="touche inconnue")
        if player.state != "connected":
            raise web.HTTPServiceUnavailable(text="Player non connecté")
        player.remote.send_key_command(code, "SHORT")
        return web.json_response({"ok": True})

    async def app_launch(request):
        name = request.match_info["name"]
        link = APPS.get(name)
        if link is None:
            raise web.HTTPNotFound(text="appli inconnue")
        if player.state != "connected":
            raise web.HTTPServiceUnavailable(text="Player non connecté")
        player.remote.send_launch_app_command(link)
        return web.json_response({"ok": True})

    async def pair_start(_):
        try:
            await player.start_pairing()
        except (CannotConnect, OSError) as err:
            raise web.HTTPBadGateway(text=str(err))
        return web.json_response({"state": player.state})

    async def pair_finish(request):
        data = await request.json()
        try:
            await player.finish_pairing(str(data.get("code", "")))
        except InvalidAuth:
            player.state = "needs_pairing"
            raise web.HTTPForbidden(text="Code incorrect")
        except (CannotConnect, OSError) as err:
            raise web.HTTPBadGateway(text=str(err))
        return web.json_response({"state": player.state})

    app = web.Application()
    app.add_routes(
        [
            web.get("/", index),
            web.get("/api/status", status),
            web.post("/api/key/{name}", key),
            web.post("/api/app/{name}", app_launch),
            web.post("/api/pair/start", pair_start),
            web.post("/api/pair/finish", pair_finish),
        ]
    )

    async def on_startup(_):
        await player.connect()
        app["retry"] = asyncio.create_task(player.retry_loop())

    async def on_cleanup(_):
        app["retry"].cancel()
        if player.remote is not None:
            player.remote.disconnect()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main():
    parser = argparse.ArgumentParser(description="Télécommande Freebox Pop")
    parser.add_argument(
        "--host",
        default=os.environ.get("FREEBOX_PLAYER_IP"),
        help="IP du Player Pop (ou variable FREEBOX_PLAYER_IP)",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    if not args.host:
        parser.error("indique l'IP du Player avec --host ou FREEBOX_PLAYER_IP")

    logging.basicConfig(level=logging.INFO)
    web.run_app(build_app(Player(args.host)), host=args.bind, port=args.port)


if __name__ == "__main__":
    main()
