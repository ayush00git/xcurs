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
git clone https://github.com/ayush00git/xcurs && cd xcurs
./install.sh
```

That's it. The installer sets up the virtual mouse (`uinput` and the `input`
group), installs xcurs, opens the firewall if needed, and runs xcurs in the
background at every login. It asks for `sudo` only where it must; see each step
first with `./install.sh --dry-run`.

## 3. Connect

Open the app on your phone, on the same Wi-Fi, within 2 minutes of installing.
It finds the laptop and pairs on its own. After that, just open the app.

To pair another phone later, run `systemctl --user restart xcurs` and open the
app within 2 minutes.

No app? Scan the QR code the installer prints, and use the touchpad in your
browser.

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
- **Pairing window closed:** `systemctl --user restart xcurs`, then open the app.
- **Is it running?** `systemctl --user status xcurs`, logs: `journalctl --user -u xcurs -f`

## Options

```bash
xcurs --pair-window 300   # allow app pairing for 5 minutes after start
xcurs --trust-wifi        # always allow app pairing (trusted networks only)
xcurs --new-token         # unpair every phone
xcurs --dry-run -v        # no mouse, just log events
```

To change how the background service runs, `systemctl --user edit xcurs` and add
(this survives updates):

```ini
[Service]
ExecStart=
ExecStart=%h/.local/bin/xcurs --pair-window 300
```

**Update:** `git pull && ./install.sh`. **Remove:** `./install.sh --uninstall`.

## Development

- Dev setup: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
- Tests: `pytest`, and `cd android && ./gradlew test`
- Build the app yourself: `cd android && ./gradlew assembleDebug`
- Release: **Actions → Android release → Run workflow**, then type a version.
  To sign releases with your own key, add the repository secrets
  `XCURS_KEYSTORE_BASE64`, `XCURS_KEYSTORE_PASSWORD`, `XCURS_KEY_ALIAS` and
  `XCURS_KEY_PASSWORD`.

## License

Apache License 2.0. See [LICENSE](LICENSE).
