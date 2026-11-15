from evdev import ecodes as e

from xcurs.pointer import VirtualPointer


class FakeDevice:
    """Records events instead of sending them to /dev/uinput."""

    def __init__(self):
        self.events = []
        self.closed = False

    def write(self, etype, code, value):
        self.events.append((etype, code, value))

    def syn(self):
        self.events.append("syn")

    def close(self):
        self.closed = True


def values(dev, code):
    return [ev[2] for ev in dev.events if ev != "syn" and ev[1] == code]


def make():
    dev = FakeDevice()
    return VirtualPointer(device=dev), dev


def test_move_writes_rel_and_syn():
    p, dev = make()
    p.move(5, -3)
    assert dev.events == [(e.EV_REL, e.REL_X, 5), (e.EV_REL, e.REL_Y, -3), "syn"]


def test_subpixel_motion_accumulates():
    p, dev = make()
    for _ in range(4):
        p.move(0.3, -0.3)
    # 1.2 -> 1 and -1.2 -> -1; the 0.2 remainder is kept for next time
    assert (sum(values(dev, e.REL_X)), sum(values(dev, e.REL_Y))) == (1, -1)


def test_tiny_move_writes_nothing():
    p, dev = make()
    p.move(0.2, 0.2)
    assert dev.events == []


def test_smooth_scroll_emits_notch_every_120():
    p, dev = make()
    for _ in range(4):
        p.scroll(dy=0.25)
    assert values(dev, e.REL_WHEEL_HI_RES) == [30, 30, 30, 30]
    assert values(dev, e.REL_WHEEL) == [1]


def test_click_and_release_all():
    p, dev = make()
    p.click("right")
    assert dev.events == [
        (e.EV_KEY, e.BTN_RIGHT, 1), "syn",
        (e.EV_KEY, e.BTN_RIGHT, 0), "syn",
    ]
    dev.events.clear()
    p.press("left")
    p.press("left")  # pressing twice is a no-op
    p.close()
    assert dev.events == [(e.EV_KEY, e.BTN_LEFT, 1), "syn", (e.EV_KEY, e.BTN_LEFT, 0), "syn"]
    assert dev.closed
