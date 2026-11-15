"""Phase 3: pairing.

Anyone on the same Wi-Fi could otherwise drive your mouse. So the daemon
keeps a random secret token, and the phone must present it to open the
WebSocket. The token travels inside the QR code's URL, after the '#', a part
of a URL that browsers never send to servers, so it stays out of request
logs. The page reads it and remembers it.
"""

from __future__ import annotations

import hmac
import os
import secrets
import sys
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
