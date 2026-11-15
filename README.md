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

## Phase 3: polish

**Pairing.** On first run xcurs makes a secret token (`~/.config/xcurs/token`)
and prints a QR code. Scan it once; the phone remembers the token. Without it
the WebSocket is refused, so nobody else on the Wi-Fi can drive your mouse.

```bash
xcurs --pair        # show the QR again
xcurs --new-token   # unpair every phone
```

**Settings.** Tap `···` on the phone for sensitivity, acceleration, scroll
speed, natural scrolling and haptics. They're saved on the phone.
Tip: use your browser's "Add to Home screen" to get a full-screen app.

**Run at login** (systemd user service):

```bash
pipx install .                                   # puts xcurs in ~/.local/bin
mkdir -p ~/.config/systemd/user
cp packaging/xcurs.service ~/.config/systemd/user/
systemctl --user enable --now xcurs
journalctl --user -u xcurs -f                    # logs
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

## V2.1: beacon + Android app

The laptop now announces itself on the Wi-Fi over mDNS (`_xcurs._tcp`), and
the Android app in `android/` finds it on its own: no typing addresses, and it
survives the laptop's IP changing. The app shows the same touchpad page.

**Build and install the app** (Android Studio, or the command line with the
Android SDK installed):

```bash
cd android
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

**First run:** start `xcurs` on the laptop, open the app, tap **scan qr**.
After that the app just finds the laptop by itself.

If the app can't find the laptop, allow mDNS through the firewall
(`sudo ufw allow 5353/udp`, or `sudo firewall-cmd --add-service=mdns`). The app
then falls back to the last address that worked. Use `xcurs --no-mdns` to
stop announcing.

## V2.2: knock to open

Knock three times on the back of your phone and xcurs opens, already
connected to your laptop.

- After the first pairing the app offers to turn it on. You can also add the
  **xcurs knock** tile to Quick Settings and toggle it there.
- Allow **Display over other apps** when asked: that's what lets Android open
  xcurs from the background. Without it, a knock shows a notification to tap.
- While it listens there's a small silent notification (Android requires one).
  It only listens while the screen is on, and turns itself back on after a reboot.

Knocks are recognised in `KnockDetector.kt`: short, sharp spikes in the
accelerometer, three in a row, starting while the phone is still. Walking and
shaking don't count. Run its tests with `./gradlew test`.

## Releases: install the app without building

Every tag like `v0.5.0` makes GitHub Actions build a signed APK and attach it
to a [GitHub Release](../../releases). On the phone: download it, tap it, and
allow installing from this source.

**One-time setup (the signing key).** Android only installs an update over an
existing app if both are signed with the same key, so create one and keep it safe:

```bash
keytool -genkeypair -v -keystore xcurs-release.jks -alias xcurs -keyalg RSA -keysize 4096 -validity 10000
```

Then add four repository secrets (Settings → Secrets and variables → Actions):

| Secret                    | Value                                  |
|---------------------------|----------------------------------------|
| `XCURS_KEYSTORE_BASE64`   | output of `base64 -w0 xcurs-release.jks` |
| `XCURS_KEYSTORE_PASSWORD` | the keystore password                  |
| `XCURS_KEY_ALIAS`         | `xcurs`                                |
| `XCURS_KEY_PASSWORD`      | the key password                       |

**Release:**

```bash
git tag v0.5.0 && git push origin v0.5.0
```

Without the secrets the workflow still works, but signs with a throwaway key,
so each release would need an uninstall first.
