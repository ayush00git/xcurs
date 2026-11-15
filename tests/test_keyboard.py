from evdev import ecodes as e

from xcurs.keyboard import VirtualKeyboard
from xcurs.pointer import VirtualPointer
from xcurs.server import handle_message
from test_pointer import FakeDevice


def keys(dev):
    """Key events as readable strings: '+A' pressed, '-A' released."""
    out = []
    for ev in dev.events:
        if ev == "syn":
            continue
        name = e.KEY[ev[1]]
        name = name[0] if isinstance(name, list) else name
        out.append(("+" if ev[2] else "-") + name.replace("KEY_", ""))
    return out


def make():
    dev = FakeDevice()
    return VirtualKeyboard(device=dev), dev


def test_types_lowercase_uppercase_and_symbols():
    kb, dev = make()
    kb.type_text("hI!")
    assert keys(dev) == [
        "+H", "-H",
        "+LEFTSHIFT", "+I", "-I", "-LEFTSHIFT",
        "+LEFTSHIFT", "+1", "-1", "-LEFTSHIFT",
    ]


def test_newline_is_enter_and_unicode_uses_ctrl_shift_u():
    kb, dev = make()
    kb.type_text("\né")
    assert keys(dev)[:2] == ["+ENTER", "-ENTER"]
    assert keys(dev)[2:8] == ["+LEFTCTRL", "+LEFTSHIFT", "+U", "-U", "-LEFTSHIFT", "-LEFTCTRL"]
    assert keys(dev)[8:] == ["+E", "-E", "+9", "-9", "+SPACE", "-SPACE"]  # U+00E9


def test_shortcuts():
    kb, dev = make()
    assert kb.press("c", ["ctrl"])
    assert keys(dev) == ["+LEFTCTRL", "+C", "-C", "-LEFTCTRL"]
    dev.events.clear()
    assert kb.press("left", ["super"])
    assert keys(dev) == ["+LEFTMETA", "+LEFT", "-LEFT", "-LEFTMETA"]
    assert not kb.press("nope")
    assert not kb.press("c", ["hyper"])


def test_messages():
    pointer = VirtualPointer(device=FakeDevice())
    kb, dev = make()
    assert handle_message(pointer, ["k", "ok"], keyboard=kb)
    assert handle_message(pointer, ["key", "enter", []], keyboard=kb)
    assert not handle_message(pointer, ["key", "enter", "ctrl"], keyboard=kb)
    assert not handle_message(pointer, ["k", 5], keyboard=kb)
    assert keys(dev) == ["+O", "-O", "+K", "-K", "+ENTER", "-ENTER"]
