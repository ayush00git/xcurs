"""A virtual mouse built on the kernel's uinput module.

uinput lets a userspace program create an input device that the kernel treats
like real hardware. Every program above the kernel (X11, Wayland compositors,
the console) sees an ordinary mouse, so nothing here is display-server specific.

An input device speaks in *events*: (type, code, value) triples.

  EV_REL / REL_X, REL_Y    relative motion in pixels ("moved 3 right")
  EV_REL / REL_WHEEL       scroll, in notches (one click of a wheel)
  EV_REL / REL_*_HI_RES    scroll in 1/120ths of a notch, for smooth scrolling
  EV_KEY / BTN_LEFT ...    buttons: value 1 = pressed, 0 = released
  EV_SYN / SYN_REPORT      "end of frame": apply everything since the last one
"""

from __future__ import annotations

from evdev import UInput, ecodes as e

BUTTONS = {
    "left": e.BTN_LEFT,
    "right": e.BTN_RIGHT,
    "middle": e.BTN_MIDDLE,
}

# What our device claims it can do. The kernel rejects events outside this set.
CAPABILITIES = {
    e.EV_KEY: list(BUTTONS.values()),
    e.EV_REL: [
        e.REL_X,
        e.REL_Y,
        e.REL_WHEEL,
        e.REL_HWHEEL,
        e.REL_WHEEL_HI_RES,
        e.REL_HWHEEL_HI_RES,
    ],
}

HI_RES_PER_NOTCH = 120  # kernel convention for REL_WHEEL_HI_RES


class _Axis:
    """Accumulates fractional input and hands out whole units.

    A phone reports motion like 0.4px, 0.7px, 0.3px. The kernel only takes
    integers, so we keep the leftover fraction and carry it into the next call;
    otherwise slow finger movement would be rounded away to nothing.
    """

    def __init__(self) -> None:
        self.rest = 0.0

    def take(self, amount: float) -> int:
        self.rest += amount
        whole = int(self.rest)  # truncates toward zero, for both directions
        self.rest -= whole
        return whole


class VirtualPointer:
    """A mouse that exists only in software.

    Scroll uses kernel semantics: positive dy scrolls up, positive dx scrolls
    right. ``device`` is injectable so tests can run without /dev/uinput.
    """

    def __init__(self, name: str = "xcurs virtual pointer", device=None) -> None:
        self._dev = device if device is not None else UInput(CAPABILITIES, name=name)
        self._x, self._y = _Axis(), _Axis()
        self._wheel_hi, self._hwheel_hi = _Axis(), _Axis()
        self._wheel_notch, self._hwheel_notch = _Axis(), _Axis()
        self._held: set[str] = set()

    # -- motion -----------------------------------------------------------

    def move(self, dx: float, dy: float) -> None:
        ix, iy = self._x.take(dx), self._y.take(dy)
        if ix:
            self._dev.write(e.EV_REL, e.REL_X, ix)
        if iy:
            self._dev.write(e.EV_REL, e.REL_Y, iy)
        if ix or iy:
            self._dev.syn()

    def scroll(self, dx: float = 0.0, dy: float = 0.0) -> None:
        """Scroll by (possibly fractional) notches.

        Real smooth-scrolling mice send both: the hi-res value for modern apps,
        and a whole notch every time 120 hi-res units add up, for older ones.
        """
        wrote = False
        for amount, hi_axis, notch_axis, hi_code, notch_code in (
            (dy, self._wheel_hi, self._wheel_notch, e.REL_WHEEL_HI_RES, e.REL_WHEEL),
            (dx, self._hwheel_hi, self._hwheel_notch, e.REL_HWHEEL_HI_RES, e.REL_HWHEEL),
        ):
            hi = hi_axis.take(amount * HI_RES_PER_NOTCH)
            if not hi:
                continue
            self._dev.write(e.EV_REL, hi_code, hi)
            notches = notch_axis.take(hi / HI_RES_PER_NOTCH)
            if notches:
                self._dev.write(e.EV_REL, notch_code, notches)
            wrote = True
        if wrote:
            self._dev.syn()

    # -- buttons ----------------------------------------------------------

    def press(self, button: str = "left") -> None:
        if button in self._held:
            return
        self._dev.write(e.EV_KEY, BUTTONS[button], 1)
        self._dev.syn()
        self._held.add(button)

    def release(self, button: str = "left") -> None:
        if button not in self._held:
            return
        self._dev.write(e.EV_KEY, BUTTONS[button], 0)
        self._dev.syn()
        self._held.discard(button)

    def click(self, button: str = "left") -> None:
        self.press(button)
        self.release(button)

    def release_all(self) -> None:
        """Never leave a button stuck down (e.g. when the phone disconnects)."""
        for button in list(self._held):
            self.release(button)

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        self.release_all()
        self._dev.close()

    def __enter__(self) -> "VirtualPointer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
