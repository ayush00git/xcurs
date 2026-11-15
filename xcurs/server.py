"""The daemon: the thread between phone and laptop.

The daemon serves the touchpad page over HTTP and listens on a WebSocket.
The phone sends small JSON arrays, and each one becomes a mouse event:

    ["m", dx, dy]   move the cursor by dx, dy pixels
    ["s", dx, dy]   scroll by dx, dy notches (kernel signs: +dy = up)
    ["c", button]   click   (button: "left" | "right" | "middle")
    ["d", button]   press and hold (start a drag)
    ["u", button]   release
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import socket
from pathlib import Path

from aiohttp import WSMsgType, web

from .beacon import Beacon
from .pairing import load_token, pair_url, print_pairing, token_ok
from .pointer import BUTTONS, VirtualPointer

log = logging.getLogger("xcurs")

WEB_DIR = Path(__file__).parent / "web"
MAX_STEP = 2000.0  # ignore absurd values instead of flinging the cursor away
POINTER = web.AppKey("pointer", VirtualPointer)
TOKEN = web.AppKey("token", str)  # empty string = pairing disabled


def _number(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    if not math.isfinite(v):
        return None
    return max(-MAX_STEP, min(MAX_STEP, v))


def handle_message(pointer: VirtualPointer, msg) -> bool:
    """Apply one message to the pointer. Returns False if it was malformed."""
    if not isinstance(msg, list) or not msg:
        return False
    kind, args = msg[0], msg[1:]

    if kind in ("m", "s") and len(args) == 2:
        dx, dy = _number(args[0]), _number(args[1])
        if dx is None or dy is None:
            return False
        (pointer.move if kind == "m" else pointer.scroll)(dx, dy)
        return True

    if kind in ("c", "d", "u") and len(args) == 1 and args[0] in BUTTONS:
        {"c": pointer.click, "d": pointer.press, "u": pointer.release}[kind](args[0])
        return True

    return False


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    if not _authorized(request):
        log.warning("rejected unpaired phone: %s", request.remote)
        raise web.HTTPUnauthorized()
    pointer = request.app[POINTER]
    ws = web.WebSocketResponse(heartbeat=10)
    await ws.prepare(request)
    log.info("phone connected: %s", request.remote)
    try:
        async for frame in ws:
            if frame.type != WSMsgType.TEXT:
                continue
            try:
                msg = json.loads(frame.data)
            except ValueError:
                continue
            # A frame may carry one message or a batch of them.
            batch = msg if isinstance(msg, list) and msg and isinstance(msg[0], list) else [msg]
            for m in batch:
                handle_message(pointer, m)
    finally:
        # The phone vanished mid-drag? Don't leave the button held down.
        pointer.release_all()
        log.info("phone disconnected: %s", request.remote)
    return ws


def _authorized(request: web.Request) -> bool:
    expected = request.app[TOKEN]
    return not expected or token_ok(expected, request.query.get("t"))


async def check(request: web.Request) -> web.Response:
    """Lets the page tell "wrong token" apart from "laptop unreachable"."""
    return web.Response(status=204 if _authorized(request) else 401)


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


def make_app(pointer: VirtualPointer, token: str = "") -> web.Application:
    app = web.Application()
    app[POINTER] = pointer
    app[TOKEN] = token
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/check", check)
    app.router.add_static("/static/", WEB_DIR)

    async def close_pointer(app: web.Application) -> None:
        app[POINTER].close()

    app.on_cleanup.append(close_pointer)
    return app


def lan_ip() -> str:
    """The address other devices on the Wi-Fi can reach us at.

    Connecting a UDP socket sends nothing, but makes the OS pick the
    outgoing interface, whose address is what we want.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class _LoggingDevice:
    """Stands in for /dev/uinput with --dry-run: prints events instead."""

    def write(self, etype, code, value):
        log.debug("event type=%s code=%s value=%s", etype, code, value)

    def syn(self):
        pass

    def close(self):
        pass


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="xcurs", description="Use your phone as a touchpad.")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8710)
    p.add_argument("--dry-run", action="store_true", help="don't touch /dev/uinput, just log")
    p.add_argument("--pair", action="store_true", help="show the pairing QR code and exit")
    p.add_argument("--new-token", action="store_true", help="forget paired phones, make a new token")
    p.add_argument("--no-auth", action="store_true", help="skip pairing (trusted networks only)")
    p.add_argument("--no-mdns", action="store_true", help="don't announce on the network")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    token = "" if args.no_auth else load_token(rotate=args.new_token)
    url = pair_url(lan_ip(), args.port, token) if token else f"http://{lan_ip()}:{args.port}/"
    if args.pair:
        print_pairing(url)
        return

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    device = _LoggingDevice() if args.dry_run else None
    try:
        pointer = VirtualPointer(device=device)
    except (PermissionError, FileNotFoundError) as err:
        raise SystemExit(
            f"Can't open /dev/uinput ({err}).\n"
            "See the README setup: modprobe uinput, the udev rule and the input group."
        )

    print_pairing(url)
    app = make_app(pointer, token)
    if not args.no_mdns:
        Beacon(lan_ip(), args.port, token).attach(app)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
