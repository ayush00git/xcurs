"""A virtual multitouch touchpad, for 3- and 4-finger desktop gestures.

The virtual *mouse* (pointer.py) can move and click, but desktop gestures
(GNOME's workspace swipe, KDE's overview, ...) are recognised by libinput only
on a touchpad, from several fingers moving together. So xcurs also creates a
touchpad and, when you swipe with 3 or 4 fingers on the phone, plays that
swipe on it. The desktop then does whatever it normally does for that gesture.

Multitouch uses the kernel's "type B" protocol: each finger lives in a slot.

  ABS_MT_SLOT n              the following events are about finger n
  ABS_MT_TRACKING_ID id      this slot now holds a finger (-1: lifted)
  ABS_MT_POSITION_X/Y        where that finger is
  BTN_TOOL_TRIPLETAP ...     how many fingers are down, for libinput

The phone's fingers can land anywhere, which might look like a thumb resting
on a real touchpad. So we don't copy them: we place 3 or 4 tidy fingers side
by side and move them together by the average motion of the real ones.
"""

from __future__ import annotations

from evdev import AbsInfo, UInput, ecodes as e

RES = 25                        # units per mm
WIDTH_MM, HEIGHT_MM = 160, 100  # a large laptop touchpad
MAX_X, MAX_Y = WIDTH_MM * RES, HEIGHT_MM * RES
FINGER_GAP_MM = 18
MAX_FINGERS = 4

TOOLS = {
    1: e.BTN_TOOL_FINGER,
    2: e.BTN_TOOL_DOUBLETAP,
    3: e.BTN_TOOL_TRIPLETAP,
    4: e.BTN_TOOL_QUADTAP,
}

CAPABILITIES = {
    e.EV_KEY: [e.BTN_LEFT, e.BTN_TOUCH, *TOOLS.values()],
    e.EV_ABS: [
        (e.ABS_X, AbsInfo(0, 0, MAX_X, 0, 0, RES)),
        (e.ABS_Y, AbsInfo(0, 0, MAX_Y, 0, 0, RES)),
        (e.ABS_MT_SLOT, AbsInfo(0, 0, MAX_FINGERS - 1, 0, 0, 0)),
        (e.ABS_MT_TRACKING_ID, AbsInfo(0, 0, 65535, 0, 0, 0)),
        (e.ABS_MT_POSITION_X, AbsInfo(0, 0, MAX_X, 0, 0, RES)),
        (e.ABS_MT_POSITION_Y, AbsInfo(0, 0, MAX_Y, 0, 0, RES)),
    ],
}


class VirtualTouchpad:
    """Plays multi-finger swipes. ``device`` is injectable for tests."""

    def __init__(self, name: str = "xcurs virtual touchpad", device=None) -> None:
        self._dev = device if device is not None else UInput(
            CAPABILITIES,
            name=name,
            # A pointer device with a clickpad: what udev and libinput expect
            # of a laptop touchpad.
            input_props=[e.INPUT_PROP_POINTER, e.INPUT_PROP_BUTTONPAD],
        )
        self.fingers = 0
        self._cx = self._cy = 0.0
        self._next_id = 0

    def swipe(self, fingers: int, dx_mm: float, dy_mm: float) -> None:
        """Move ``fingers`` (3 or 4) together by dx, dy millimetres.

        A new finger count starts a new gesture; 0 lifts all fingers.
        """
        if fingers != self.fingers:
            self.lift()
            if fingers in (3, 4):
                self._land(fingers)
        if not self.fingers or (not dx_mm and not dy_mm):
            return
        self._cx += dx_mm * RES
        self._cy += dy_mm * RES
        self._clamp()
        self._write_positions()
        self._dev.syn()

    def lift(self) -> None:
        if not self.fingers:
            return
        for slot in range(self.fingers):
            self._dev.write(e.EV_ABS, e.ABS_MT_SLOT, slot)
            self._dev.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, -1)
        self._dev.write(e.EV_KEY, e.BTN_TOUCH, 0)
        self._dev.write(e.EV_KEY, TOOLS[self.fingers], 0)
        self._dev.syn()
        self.fingers = 0

    def close(self) -> None:
        self.lift()
        self._dev.close()

    # -- internals ----------------------------------------------------------

    def _land(self, fingers: int) -> None:
        self.fingers = fingers
        self._cx, self._cy = MAX_X / 2, MAX_Y / 2
        for slot in range(fingers):
            self._dev.write(e.EV_ABS, e.ABS_MT_SLOT, slot)
            self._dev.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, self._next_id)
            self._next_id = (self._next_id + 1) % 65536
        self._write_positions()
        self._dev.write(e.EV_KEY, e.BTN_TOUCH, 1)
        self._dev.write(e.EV_KEY, TOOLS[fingers], 1)
        self._dev.syn()

    def _offsets(self) -> list[float]:
        gap = FINGER_GAP_MM * RES
        return [(i - (self.fingers - 1) / 2) * gap for i in range(self.fingers)]

    def _clamp(self) -> None:
        # Keep every finger on the pad; at the edge the swipe just stops.
        half = (self.fingers - 1) / 2 * FINGER_GAP_MM * RES
        self._cx = min(max(self._cx, half), MAX_X - half)
        self._cy = min(max(self._cy, 0), MAX_Y)

    def _write_positions(self) -> None:
        y = round(self._cy)
        for slot, off in enumerate(self._offsets()):
            x = round(self._cx + off)
            self._dev.write(e.EV_ABS, e.ABS_MT_SLOT, slot)
            self._dev.write(e.EV_ABS, e.ABS_MT_POSITION_X, x)
            self._dev.write(e.EV_ABS, e.ABS_MT_POSITION_Y, y)
            if slot == 0:  # single-touch axes mirror the first finger
                self._dev.write(e.EV_ABS, e.ABS_X, x)
                self._dev.write(e.EV_ABS, e.ABS_Y, y)
