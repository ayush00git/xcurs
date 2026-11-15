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
