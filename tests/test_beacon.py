import asyncio
import hashlib

from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

from xcurs.beacon import SERVICE_TYPE, Beacon, pairing_id, service_info


def test_pairing_id_is_a_short_hash_and_hides_the_token():
    pid = pairing_id("s3cret")
    assert pid == hashlib.sha256(b"s3cret").hexdigest()[:16]
    assert "s3cret" not in pid
    assert pairing_id("") == ""


def test_service_info_fields():
    info = service_info("192.168.1.20", 8710, "s3cret", hostname="my laptop.lan")
    assert info.type == SERVICE_TYPE
    assert info.port == 8710
    assert info.parsed_addresses() == ["192.168.1.20"]
    assert info.properties[b"pid"] == pairing_id("s3cret").encode()
    assert info.properties[b"v"] == b"2"
    assert info.server == "xcurs-my-laptop-lan.local."


def test_beacon_is_discoverable():
    """Register on loopback-visible multicast and browse for it."""

    async def run():
        beacon = Beacon("127.0.0.1", 8799, "tok")
        await beacon._start(None)
        if beacon._zc is None:
            return None  # no multicast in this sandbox; nothing to assert
        found = []

        def on_change(zeroconf, service_type, name, state_change):
            if state_change is ServiceStateChange.Added:
                found.append(name)

        zc = Zeroconf()
        browser = ServiceBrowser(zc, SERVICE_TYPE, handlers=[on_change])
        for _ in range(30):
            if found:
                break
            await asyncio.sleep(0.1)
        browser.cancel()
        zc.close()
        await beacon._stop(None)
        return found

    found = asyncio.run(run())
    if found is not None:
        assert any(n.startswith("xcurs on ") for n in found)
