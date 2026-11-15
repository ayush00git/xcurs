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
