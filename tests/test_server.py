import asyncio
import json

from aiohttp.test_utils import TestClient, TestServer
from evdev import ecodes as e

from xcurs.pointer import VirtualPointer
from xcurs.server import handle_message, make_app
from test_pointer import FakeDevice, values


def test_handle_message_valid_and_invalid():
    dev = FakeDevice()
    p = VirtualPointer(device=dev)
    assert handle_message(p, ["m", 3, 4])
    assert handle_message(p, ["c", "left"])
    assert not handle_message(p, ["c", "nose"])
    assert not handle_message(p, ["m", "3", 4])
    assert not handle_message(p, ["m", float("nan"), 1])
    assert not handle_message(p, {"m": 1})
    assert not handle_message(p, [])
    assert values(dev, e.REL_X) == [3]


def test_huge_values_are_clamped():
    dev = FakeDevice()
    p = VirtualPointer(device=dev)
    handle_message(p, ["m", 1e9, 0])
    assert values(dev, e.REL_X) == [2000]


def test_websocket_batch_and_release_on_disconnect():
    async def run():
        dev = FakeDevice()
        client = TestClient(TestServer(make_app(VirtualPointer(device=dev))))
        await client.start_server()
        try:
            page = await client.get("/")
            assert page.status == 200 and "xcurs" in await page.text()
            assert (await client.get("/static/app.js")).status == 200

            ws = await client.ws_connect("/ws")
            await ws.send_str(json.dumps([["m", 10, -2], ["d", "left"]]))
            await ws.send_str("not json")
            await ws.send_str(json.dumps(["s", 0, 1]))
            await ws.close()
            await asyncio.sleep(0.05)
        finally:
            await client.close()
        return dev

    dev = asyncio.run(run())
    assert values(dev, e.REL_X) == [10]
    assert values(dev, e.REL_WHEEL) == [1]
    # held during the drag, then released when the phone went away
    assert values(dev, e.BTN_LEFT) == [1, 0]


def test_websocket_requires_token():
    async def run():
        client = TestClient(TestServer(make_app(VirtualPointer(device=FakeDevice()), token="s3cret")))
        await client.start_server()
        try:
            assert (await client.get("/check?t=nope")).status == 401
            assert (await client.get("/check?t=s3cret")).status == 204
            assert (await client.get("/ws?t=nope")).status == 401
            ws = await client.ws_connect("/ws?t=s3cret")
            await ws.close()
        finally:
            await client.close()

    asyncio.run(run())


def test_token_persists_and_rotates(tmp_path, monkeypatch):
    from xcurs.pairing import load_token

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    first = load_token()
    assert load_token() == first
    assert (tmp_path / "xcurs" / "token").stat().st_mode & 0o777 == 0o600
    assert load_token(rotate=True) != first


def _pair_status(window, body=None):
    async def run():
        app = make_app(VirtualPointer(device=FakeDevice()), token="s3cret", window=window)
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            r = await client.post("/pair", json=body or {"name": "Pixel 9"})
            return r.status, await r.json()
        finally:
            await client.close()

    return asyncio.run(run())


def test_pair_hands_out_token_while_window_open():
    from xcurs.pairing import PairingWindow

    assert _pair_status(PairingWindow(60)) == (200, {"token": "s3cret"})


def test_pair_refused_after_window_closes():
    from xcurs.pairing import PairingWindow

    t = [0.0]
    window = PairingWindow(60, clock=lambda: t[0])
    t[0] = 61
    status, body = _pair_status(window)
    assert status == 403 and "token" not in body


def test_trust_wifi_keeps_window_open():
    from xcurs.pairing import PairingWindow

    t = [0.0]
    window = PairingWindow(0, always=True, clock=lambda: t[0])
    t[0] = 10_000
    assert window.is_open()


def test_is_local():
    from xcurs.pairing import is_local

    assert is_local("192.168.1.7") and is_local("10.0.0.2") and is_local("127.0.0.1")
    assert is_local("fe80::1%wlan0")
    assert not is_local("8.8.8.8") and not is_local(None) and not is_local("junk")
