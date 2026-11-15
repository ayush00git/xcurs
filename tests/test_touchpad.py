from evdev import ecodes as e

from xcurs.server import handle_message
from xcurs.pointer import VirtualPointer
from xcurs.touchpad import FINGER_GAP_MM, MAX_X, RES, VirtualTouchpad
from test_pointer import FakeDevice


def events(dev, etype, code):
    return [ev[2] for ev in dev.events if ev != "syn" and ev[0] == etype and ev[1] == code]


def make():
    dev = FakeDevice()
    return VirtualTouchpad(device=dev), dev


def test_three_finger_swipe_lands_moves_and_lifts():
    pad, dev = make()
    pad.swipe(3, 0, 0)
    # three slots with fresh tracking ids, BTN_TOUCH and the triple-tap tool
    assert events(dev, e.EV_ABS, e.ABS_MT_TRACKING_ID) == [0, 1, 2]
    assert events(dev, e.EV_KEY, e.BTN_TOUCH) == [1]
    assert events(dev, e.EV_KEY, e.BTN_TOOL_TRIPLETAP) == [1]
    xs = events(dev, e.EV_ABS, e.ABS_MT_POSITION_X)
    assert xs == [MAX_X // 2 - FINGER_GAP_MM * RES, MAX_X // 2, MAX_X // 2 + FINGER_GAP_MM * RES]

    dev.events.clear()
    pad.swipe(3, 10, 0)  # 10 mm right: every finger moves 250 units
    assert events(dev, e.EV_ABS, e.ABS_MT_POSITION_X) == [x + 10 * RES for x in xs]

    dev.events.clear()
    pad.swipe(0, 0, 0)
    assert events(dev, e.EV_ABS, e.ABS_MT_TRACKING_ID) == [-1, -1, -1]
    assert events(dev, e.EV_KEY, e.BTN_TOUCH) == [0]
    assert events(dev, e.EV_KEY, e.BTN_TOOL_TRIPLETAP) == [0]
    assert pad.fingers == 0


def test_switching_to_four_fingers_restarts_the_gesture():
    pad, dev = make()
    pad.swipe(3, 5, 0)
    dev.events.clear()
    pad.swipe(4, 0, 5)
    assert events(dev, e.EV_KEY, e.BTN_TOOL_TRIPLETAP) == [0]
    assert events(dev, e.EV_KEY, e.BTN_TOOL_QUADTAP) == [1]
    assert events(dev, e.EV_ABS, e.ABS_MT_TRACKING_ID)[-4:] == [3, 4, 5, 6]


def test_fingers_stay_on_the_pad():
    pad, dev = make()
    pad.swipe(3, 10_000, -10_000)
    xs = events(dev, e.EV_ABS, e.ABS_MT_POSITION_X)[-3:]
    ys = events(dev, e.EV_ABS, e.ABS_MT_POSITION_Y)[-3:]
    assert max(xs) == MAX_X and min(ys) == 0


def test_swipe_message_routing():
    pointer = VirtualPointer(device=FakeDevice())
    pad, dev = make()
    assert handle_message(pointer, ["t", 3, 4.5, -2], pad)
    assert pad.fingers == 3
    assert handle_message(pointer, ["t", 0, 0, 0], pad)
    assert pad.fingers == 0
    assert not handle_message(pointer, ["t", 2, 1, 1], pad)    # 2 fingers = scroll, not a gesture
    assert not handle_message(pointer, ["t", True, 1, 1], pad)
    assert handle_message(pointer, ["t", 3, 1, 1], None)       # no touchpad: ignored, not an error
