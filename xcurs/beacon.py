"""V2: the beacon.

The laptop announces itself on the Wi-Fi with mDNS (multicast DNS, the same
thing printers and Chromecasts use), so the phone app can find it without
anyone typing an IP address.

We advertise a service of type ``_xcurs._tcp``. Alongside the address and
port, mDNS carries a few small text fields (TXT records). One of them, ``pid``,
is a hash of the pairing token. A phone that already holds the token
recognises *its* laptop among several, and the token itself never goes on air.
"""

from __future__ import annotations

import hashlib
import logging
import re
import socket

from aiohttp import web

log = logging.getLogger("xcurs")

SERVICE_TYPE = "_xcurs._tcp.local."
PROTOCOL_VERSION = "2"


def pairing_id(token: str) -> str:
    """A public fingerprint of the token: sha256, first 16 hex chars."""
    return hashlib.sha256(token.encode()).hexdigest()[:16] if token else ""


def _label(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", text).strip("-")[:40] or "laptop"


def service_info(ip: str, port: int, token: str, hostname: str | None = None):
    from zeroconf import ServiceInfo

    host = hostname or socket.gethostname()
    return ServiceInfo(
        SERVICE_TYPE,
        f"xcurs on {host[:40]}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={
            "v": PROTOCOL_VERSION,
            "pid": pairing_id(token),
            "auth": "1" if token else "0",
        },
        # Our own host record, so we never fight avahi over "<hostname>.local".
        server=f"xcurs-{_label(host)}.local.",
    )


class Beacon:
    """Registers the service while the web app runs, and withdraws it on exit."""

    def __init__(self, ip: str, port: int, token: str) -> None:
        self.info = service_info(ip, port, token)
        self._zc = None

    def attach(self, app: web.Application) -> None:
        app.on_startup.append(self._start)
        app.on_cleanup.append(self._stop)

    async def _start(self, app: web.Application) -> None:
        try:
            from zeroconf.asyncio import AsyncZeroconf

            self._zc = AsyncZeroconf()
            await self._zc.async_register_service(self.info)
            log.info("announcing on the network as %r", self.info.name.split(".")[0])
        except Exception as err:  # discovery is a convenience, never fatal
            log.warning("mDNS announcement failed (%s); phones can still use the QR URL", err)
            self._zc = None

    async def _stop(self, app: web.Application) -> None:
        if self._zc is not None:
            await self._zc.async_unregister_service(self.info)
            await self._zc.async_close()
