"""A virtual keyboard, for typing from the phone.

Keyboards don't send characters, they send *keys*; the desktop turns keys into
characters with its keyboard layout. So to type "A" we press Shift and the A
key. The table below is the US layout, the default on most Linux desktops.

Characters that aren't on the US layout (é, ₹, emoji) use the Unicode entry
that GTK apps and IBus understand: Ctrl+Shift+U, the hex code, then Space.
Where that isn't supported the character is skipped.
"""

from __future__ import annotations

import string

from evdev import UInput, ecodes as e

# character -> (key, needs shift)
CHARS: dict[str, tuple[int, bool]] = {}
for _c in string.ascii_lowercase:
    CHARS[_c] = (getattr(e, f"KEY_{_c.upper()}"), False)
    CHARS[_c.upper()] = (getattr(e, f"KEY_{_c.upper()}"), True)
for _plain, _shifted, _key in zip("1234567890", "!@#$%^&*()", "1234567890"):
    CHARS[_plain] = (getattr(e, f"KEY_{_key}"), False)
    CHARS[_shifted] = (getattr(e, f"KEY_{_key}"), True)
for _plain, _shifted, _key in (
    ("`", "~", e.KEY_GRAVE),
    ("-", "_", e.KEY_MINUS),
    ("=", "+", e.KEY_EQUAL),
    ("[", "{", e.KEY_LEFTBRACE),
    ("]", "}", e.KEY_RIGHTBRACE),
    ("\\", "|", e.KEY_BACKSLASH),
    (";", ":", e.KEY_SEMICOLON),
    ("'", '"', e.KEY_APOSTROPHE),
    (",", "<", e.KEY_COMMA),
    (".", ">", e.KEY_DOT),
    ("/", "?", e.KEY_SLASH),
):
    CHARS[_plain] = (_key, False)
    CHARS[_shifted] = (_key, True)
CHARS[" "] = (e.KEY_SPACE, False)
CHARS["\t"] = (e.KEY_TAB, False)
CHARS["\n"] = (e.KEY_ENTER, False)

# named keys the phone's key row can send
NAMED = {
    "esc": e.KEY_ESC,
    "tab": e.KEY_TAB,
    "enter": e.KEY_ENTER,
    "backspace": e.KEY_BACKSPACE,
    "delete": e.KEY_DELETE,
    "left": e.KEY_LEFT,
    "right": e.KEY_RIGHT,
    "up": e.KEY_UP,
    "down": e.KEY_DOWN,
    "home": e.KEY_HOME,
    "end": e.KEY_END,
    "pageup": e.KEY_PAGEUP,
    "pagedown": e.KEY_PAGEDOWN,
    "space": e.KEY_SPACE,
}

MODIFIERS = {
    "ctrl": e.KEY_LEFTCTRL,
    "alt": e.KEY_LEFTALT,
    "shift": e.KEY_LEFTSHIFT,
    "super": e.KEY_LEFTMETA,
}

MAX_TEXT = 500

CAPABILITIES = {
    e.EV_KEY: sorted(
        {k for k, _ in CHARS.values()}
        | set(NAMED.values())
        | set(MODIFIERS.values())
        | {getattr(e, f"KEY_{c}") for c in "0123456789ABCDEF"}
    ),
}


class VirtualKeyboard:
    """Types text and shortcuts. ``device`` is injectable for tests."""

    def __init__(self, name: str = "xcurs virtual keyboard", device=None) -> None:
        self._dev = device if device is not None else UInput(CAPABILITIES, name=name)

    def type_text(self, text: str) -> None:
        for ch in text[:MAX_TEXT]:
            if ch in CHARS:
                key, shift = CHARS[ch]
                self._tap(key, ["shift"] if shift else [])
            elif ch == "\r":
                continue
            elif ch.isprintable():
                self._unicode(ch)

    def press(self, name: str, mods: list[str] | tuple[str, ...] = ()) -> bool:
        """A named key ("enter", "left", ...) or one character ("c"), with
        modifiers ("ctrl", "alt", "shift", "super"). False if unknown."""
        if any(m not in MODIFIERS for m in mods):
            return False
        if name in NAMED:
            key, shift = NAMED[name], False
        elif len(name) == 1 and name in CHARS:
            key, shift = CHARS[name]
        else:
            return False
        mods = list(dict.fromkeys(mods))  # no duplicates, keep order
        if shift and "shift" not in mods:
            mods.append("shift")
        self._tap(key, mods)
        return True

    def close(self) -> None:
        self._dev.close()

    # -- internals ----------------------------------------------------------

    def _key(self, key: int, down: bool) -> None:
        self._dev.write(e.EV_KEY, key, 1 if down else 0)
        self._dev.syn()

    def _tap(self, key: int, mods: list[str]) -> None:
        for m in mods:
            self._key(MODIFIERS[m], True)
        self._key(key, True)
        self._key(key, False)
        for m in reversed(mods):
            self._key(MODIFIERS[m], False)

    def _unicode(self, ch: str) -> None:
        self._tap(e.KEY_U, ["ctrl", "shift"])
        for digit in f"{ord(ch):x}":
            self._tap(getattr(e, f"KEY_{digit.upper()}"), [])
        self._tap(e.KEY_SPACE, [])
