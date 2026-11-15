# xcurs

Your phone, as a touchpad for your Linux laptop.

A small daemon on the laptop creates a virtual mouse through the kernel's
`uinput` module, so it works on X11 and Wayland, on any distro. The phone app
finds the laptop on your Wi-Fi by itself and turns your screen into a touchpad.

## 1. Get the app

Download the latest APK from **[Releases](../../releases/latest)** and open it
on your Android phone (allow installing from your browser when asked).

## 2. Set up the laptop (once)

```bash
# let your user create a virtual mouse
sudo modprobe uinput
sudo cp packaging/uinput.conf /etc/modules-load.d/
sudo cp packaging/99-xcurs-uinput.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG input "$USER"      # then log out and back in

# install
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

Building `evdev` needs Python headers: `sudo dnf install python3-devel gcc`
(Fedora) or `sudo apt install python3-dev gcc` (Ubuntu).

## 3. Use it

```bash
xcurs
```

Open the app on your phone within 2 minutes; it finds and pairs with the
laptop on its own. After that, just open the app.

No app? Scan the QR code `xcurs` prints, and use the touchpad in your browser.

| Gesture                   | Does         |
|---------------------------|--------------|
| one finger                | move         |
| tap                       | left click   |
| two-finger tap            | right click  |
| two-finger drag           | scroll       |
| double-tap and hold, drag | drag         |

Tap `···` for sensitivity, acceleration and scroll settings.

## Troubleshooting

- **Phone can't find the laptop:** allow it through the firewall:
  `sudo ufw allow 8710/tcp && sudo ufw allow 5353/udp`
  (Fedora: `sudo firewall-cmd --add-port=8710/tcp --add-service=mdns`).
- **College or public Wi-Fi** often blocks devices from seeing each other.
  Use your phone's hotspot instead.
- **Pairing window closed:** restart `xcurs`, then open the app.

## Options

```bash
xcurs --pair-window 300   # allow app pairing for 5 minutes after start
xcurs --trust-wifi        # always allow app pairing (trusted networks only)
xcurs --new-token         # unpair every phone
xcurs --dry-run -v        # no mouse, just log events
```

**Run at login:**

```bash
pipx install .
mkdir -p ~/.config/systemd/user && cp packaging/xcurs.service ~/.config/systemd/user/
systemctl --user enable --now xcurs
```

## Development

- Tests: `pytest`, and `cd android && ./gradlew test`
- Build the app yourself: `cd android && ./gradlew assembleDebug`
- Release: **Actions → Android release → Run workflow**, then type a version.
  To sign releases with your own key, add the repository secrets
  `XCURS_KEYSTORE_BASE64`, `XCURS_KEYSTORE_PASSWORD`, `XCURS_KEY_ALIAS` and
  `XCURS_KEY_PASSWORD`.

## License

Apache License 2.0. See [LICENSE](LICENSE).
