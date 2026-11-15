"""Phase 3: pairing.

Anyone on the same Wi-Fi could otherwise drive your mouse. So the daemon
keeps a random secret token, and the phone must present it to open the
WebSocket. The token travels inside the QR code's URL, after the '#', a part
of a URL that browsers never send to servers, so it stays out of request
logs. The page reads it and remembers it.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "xcurs"


def load_token(rotate: bool = False) -> str:
    """Read the saved token, creating one (owner-readable only) if needed."""
    path = config_dir() / "token"
    if not rotate:
        try:
            token = path.read_text().strip()
            if token:
                return token
        except FileNotFoundError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(18)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token + "\n")
    return token


def token_ok(expected: str, given: str | None) -> bool:
    # compare_digest takes the same time whether the first or last char is
    # wrong, so the token can't be guessed one character at a time.
    return given is not None and hmac.compare_digest(expected.encode(), given.encode())


def pair_url(ip: str, port: int, token: str) -> str:
    return f"http://{ip}:{port}/#t={token}"


def print_pairing(url: str) -> None:
    print("\n  Scan with your phone (same Wi-Fi):\n")
    try:
        import qrcode

        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        # invert=True draws dark modules as spaces: right for dark terminals.
        qr.print_ascii(out=sys.stdout, invert=True)
    except ImportError:
        pass
    print(f"\n  or open: {url}\n")


class PairingWindow:
    """V2.4: pairing without a QR code, like Bluetooth pairing mode.

    While the window is open, the phone app can ask for the token
    (POST /pair) and gets it, no scanning needed. It opens for a short time
    when xcurs starts; after that only phones that already hold the token
    can connect. ``always`` keeps it open, for trusted home networks.
    """

    def __init__(self, seconds: float, always: bool = False, clock=time.monotonic) -> None:
        self._clock = clock
        self.always = always
        self.closes_at = clock() + max(seconds, 0)

    def is_open(self) -> bool:
        return self.always or self._clock() < self.closes_at

    def seconds_left(self) -> int:
        return max(0, round(self.closes_at - self._clock()))


def is_local(address: str | None) -> bool:
    """Only hand out the token to devices on the local network."""
    try:
        ip = ipaddress.ip_address((address or "").split("%")[0])
    except ValueError:
        return False
    return ip.is_private or ip.is_link_local or ip.is_loopback


def notify(title: str, body: str) -> None:
    """A desktop notification, so a new phone never pairs silently."""
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "--app-name=xcurs", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
