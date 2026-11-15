# xcurs

Your phone, as a touchpad for your Linux laptop.

xcurs runs a tiny daemon on the laptop that creates a virtual mouse through the
kernel's `uinput` module, and serves a touchpad page you open on your phone.
Because it talks to the kernel instead of the display server, it works the same
on X11 and Wayland, on any distro.

## Setup (once)

```bash
# 1. Load the uinput kernel module now, and on every boot
sudo modprobe uinput
sudo cp packaging/uinput.conf /etc/modules-load.d/uinput.conf

# 2. Let the "input" group use /dev/uinput, so xcurs runs without sudo
sudo cp packaging/99-xcurs-uinput.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG input "$USER"   # then log out and back in

# 3. Install
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

## Phase 1: ghost mouse

```bash
python -m xcurs.demo            # cursor draws a circle on its own
python -m xcurs.demo --shape square --scroll
pytest                          # unit tests, no /dev/uinput needed
```

While the demo runs, `libinput list-devices` (or `cat /proc/bus/input/devices`)
shows a new device called **xcurs virtual pointer**.

## Phase 2: the thread

```bash
pip install -e '.[dev]'
xcurs                 # prints a URL; open it on your phone (same Wi-Fi)
xcurs --dry-run -v    # no /dev/uinput needed, logs events instead
```

| Gesture on the phone      | On the laptop |
|---------------------------|---------------|
| one finger drag           | move cursor   |
| tap                       | left click    |
| two-finger tap            | right click   |
| three-finger tap          | middle click  |
| two-finger drag           | scroll        |
| double-tap and hold, drag | click-drag    |

If the phone can't connect, allow the port through your firewall,
e.g. `sudo ufw allow 8710/tcp`.
