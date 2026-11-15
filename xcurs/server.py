"""The daemon: the thread between phone and laptop.

The daemon serves the touchpad page over HTTP and listens on a WebSocket.
The phone sends small JSON arrays, and each one becomes a mouse event:

    ["m", dx, dy]   move the cursor by dx, dy pixels
    ["s", dx, dy]   scroll by dx, dy notches (kernel signs: +dy = up)
    ["c", button]   click   (button: "left" | "right" | "middle")
    ["d", button]   press and hold (start a drag)
    ["u", button]   release
    ["t", n, dx, dy] swipe n fingers (3 or 4) by dx, dy mm on the virtual
                    touchpad, for desktop gestures; ["t", 0, 0, 0] lifts them
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
from .pairing import (
    PairingWindow,
    is_local,
    load_token,
    notify,
    pair_url,
    print_pairing,
    token_ok,
)
from .pointer import BUTTONS, VirtualPointer
from .touchpad import VirtualTouchpad

log = logging.getLogger("xcurs")

WEB_DIR = Path(__file__).parent / "web"
MAX_STEP = 2000.0  # ignore absurd values instead of flinging the cursor away
POINTER = web.AppKey("pointer", VirtualPointer)
TOUCHPAD = web.AppKey("touchpad", object)  # VirtualTouchpad, or None if unavailable
TOKEN = web.AppKey("token", str)  # empty string = pairing disabled
WINDOW = web.AppKey("window", PairingWindow)
MAX_NAME = 60


def _number(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    if not math.isfinite(v):
        return None
    return max(-MAX_STEP, min(MAX_STEP, v))


def handle_message(pointer: VirtualPointer, msg, touchpad: VirtualTouchpad | None = None) -> bool:
    """Apply one message. Returns False if it was malformed."""
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

    if kind == "t" and len(args) == 3 and args[0] in (0, 3, 4) and not isinstance(args[0], bool):
        dx, dy = _number(args[1]), _number(args[2])
        if dx is None or dy is None:
            return False
        if touchpad is not None:
            touchpad.swipe(int(args[0]), dx, dy)
        return True

    return False


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    if not _authorized(request):
        log.warning("rejected unpaired phone: %s", request.remote)
        raise web.HTTPUnauthorized()
    pointer = request.app[POINTER]
    touchpad = request.app[TOUCHPAD]
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
                handle_message(pointer, m, touchpad)
    finally:
        # The phone vanished mid-drag? Don't leave a button or fingers down.
        pointer.release_all()
        if touchpad is not None:
            touchpad.lift()
        log.info("phone disconnected: %s", request.remote)
    return ws


def _authorized(request: web.Request) -> bool:
    expected = request.app[TOKEN]
    return not expected or token_ok(expected, request.query.get("t"))


async def check(request: web.Request) -> web.Response:
    """Lets the page tell "wrong token" apart from "laptop unreachable"."""
    return web.Response(status=204 if _authorized(request) else 401)


async def pair(request: web.Request) -> web.Response:
    """The app asks for the token here, instead of scanning the QR code."""
    window = request.app[WINDOW]
    if not is_local(request.remote):
        raise web.HTTPForbidden(text="pairing is only for the local network")
    if not window.is_open():
        return web.json_response({"error": "pairing closed"}, status=403)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    name = str(body.get("name") or "a phone")[:MAX_NAME] if isinstance(body, dict) else "a phone"
    log.info("paired with %s (%s)", name, request.remote)
    notify("xcurs: phone paired", f"{name} can now control your mouse.")
    return web.json_response({"token": request.app[TOKEN]})


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


def make_app(
    pointer: VirtualPointer,
    token: str = "",
    window: PairingWindow | None = None,
    touchpad: VirtualTouchpad | None = None,
) -> web.Application:
    app = web.Application()
    app[POINTER] = pointer
    app[TOUCHPAD] = touchpad
    app[TOKEN] = token
    app[WINDOW] = window or PairingWindow(0)
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/check", check)
    app.router.add_post("/pair", pair)
    app.router.add_static("/static/", WEB_DIR)

    async def close_pointer(app: web.Application) -> None:
        app[POINTER].close()
        if app[TOUCHPAD] is not None:
            app[TOUCHPAD].close()

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
    p.add_argument(
        "--no-gestures", action="store_true",
        help="don't create the virtual touchpad used for 3- and 4-finger gestures",
    )
    p.add_argument(
        "--pair-window", type=int, default=120, metavar="SECONDS",
        help="let the phone app pair without a QR for this long after start (0 = off)",
    )
    p.add_argument(
        "--trust-wifi", action="store_true",
        help="always let phones on this network pair (only on networks you trust)",
    )
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
    touchpad = None
    if not args.no_gestures:
        try:
            touchpad = VirtualTouchpad(device=_LoggingDevice() if args.dry_run else None)
        except Exception as err:  # gestures are a bonus; the mouse still works
            log.warning("3/4-finger gestures unavailable: %s", err)

    print_pairing(url)
    window = PairingWindow(args.pair_window, always=args.trust_wifi)
    if args.trust_wifi:
        print("  Any phone on this Wi-Fi can pair (--trust-wifi).\n")
    elif token and window.is_open():
        print(f"  Or just open the xcurs app: pairing is open for {window.seconds_left()} s.\n")
    app = make_app(pointer, token, window, touchpad)
    if not args.no_mdns:
        Beacon(lan_ip(), args.port, token).attach(app)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
