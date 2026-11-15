#!/usr/bin/env bash
# xcurs installer: sets up this Linux laptop so the xcurs phone app can drive it.
#
#   ./install.sh              install (or update, after a git pull)
#   ./install.sh --dry-run    print every step without changing anything
#   ./install.sh --uninstall  remove xcurs again
#
# Run it as your normal user; it asks for sudo only where it must.

set -euo pipefail

PORT=8710
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/xcurs"
VENV="$APP_DIR/venv"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
TOKEN_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/xcurs/token"
UDEV_RULE=/etc/udev/rules.d/99-xcurs-uinput.rules
MODULES_CONF=/etc/modules-load.d/xcurs-uinput.conf

DRY=0
MODE=install

# ---- helpers ----------------------------------------------------------------

bold=$'\033[1m' dim=$'\033[2m' reset=$'\033[0m'
[[ -t 1 ]] || bold='' dim='' reset=''

step() { printf '\n%s==> %s%s\n' "$bold" "$*" "$reset"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    %s! %s%s\n' "$bold" "$*" "$reset" >&2; }
die()  { printf '%serror:%s %s\n' "$bold" "$reset" "$*" >&2; exit 1; }

# Run a command, or only show it with --dry-run.
run() {
    if ((DRY)); then
        printf '    %s$ %s%s\n' "$dim" "$*" "$reset"
    else
        "$@"
    fi
}

as_root() { run sudo "$@"; }

usage() { sed -n '2,9s/^# \{0,1\}//p' "$0"; }

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY=1 ;;
        --uninstall) MODE=uninstall ;;
        -h | --help) usage; exit 0 ;;
        *) die "unknown option: $arg (see --help)" ;;
    esac
done

# ---- checks -----------------------------------------------------------------

preflight() {
    [[ "$(uname -s)" == Linux ]] || die "xcurs is for Linux."
    ((EUID != 0)) || die "run this as your normal user, not root. It uses sudo when it needs to."
    if ((!DRY)); then
        command -v sudo >/dev/null || die "sudo is needed for the system steps."
        command -v systemctl >/dev/null || die "systemd is needed to run xcurs in the background."
    fi
}

# ---- 1. system packages -----------------------------------------------------

install_packages() {
    step "Installing system packages (Python, and a compiler for evdev)"
    if command -v apt-get >/dev/null; then
        as_root apt-get update -qq
        as_root apt-get install -y python3 python3-venv python3-dev gcc linux-libc-dev
    elif command -v dnf >/dev/null; then
        as_root dnf install -y python3 python3-devel gcc kernel-headers
    elif command -v pacman >/dev/null; then
        as_root pacman -S --needed --noconfirm python gcc linux-api-headers
    elif command -v zypper >/dev/null; then
        as_root zypper --non-interactive install python3 python3-devel gcc linux-glibc-devel
    else
        warn "Unknown package manager: make sure python3 (with venv), its headers and gcc are installed."
    fi
}

# ---- 2. uinput access -------------------------------------------------------

setup_uinput() {
    step "Giving xcurs access to the virtual mouse (uinput)"
    as_root modprobe uinput
    as_root install -m 0644 "$REPO/packaging/uinput.conf" "$MODULES_CONF"

    if ! getent group input >/dev/null; then
        info "creating the 'input' group"
        as_root groupadd --system input
    fi
    if ! id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
        info "adding $USER to the 'input' group"
        as_root usermod -aG input "$USER"
    fi

    as_root install -m 0644 "$REPO/packaging/99-xcurs-uinput.rules" "$UDEV_RULE"
    as_root udevadm control --reload-rules
    as_root udevadm trigger --subsystem-match=misc --sysname-match=uinput --action=change
    if ((!DRY)); then
        udevadm settle 2>/dev/null || true
        if [[ -w /dev/uinput ]]; then
            info "/dev/uinput is ready"
        else
            warn "/dev/uinput isn't writable yet: log out and back in once, then it is."
        fi
    fi
}

# ---- 3. xcurs itself --------------------------------------------------------

install_xcurs() {
    step "Installing xcurs into $VENV"
    run mkdir -p "$APP_DIR" "$BIN_DIR"
    run python3 -m venv "$VENV"
    run "$VENV/bin/pip" install --quiet --upgrade pip
    run "$VENV/bin/pip" install --quiet "$REPO"
    run ln -sf "$VENV/bin/xcurs" "$BIN_DIR/xcurs"
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) warn "$BIN_DIR isn't on your PATH; add it to run 'xcurs' by hand." ;;
    esac
}

# ---- 4. firewall ------------------------------------------------------------

open_firewall() {
    step "Letting the phone through the firewall"
    if command -v ufw >/dev/null && systemctl is-active --quiet ufw 2>/dev/null; then
        as_root ufw allow "$PORT/tcp" comment xcurs
        as_root ufw allow 5353/udp comment "xcurs mDNS"
    elif command -v firewall-cmd >/dev/null && systemctl is-active --quiet firewalld 2>/dev/null; then
        as_root firewall-cmd --permanent --add-port="$PORT/tcp" --add-service=mdns
        as_root firewall-cmd --reload
    else
        info "no active ufw or firewalld found, nothing to open"
    fi
}

# ---- 5. background service --------------------------------------------------

start_service() {
    step "Running xcurs in the background (starts at every login)"
    run mkdir -p "$UNIT_DIR"
    run install -m 0644 "$REPO/packaging/xcurs.service" "$UNIT_DIR/xcurs.service"
    run systemctl --user daemon-reload
    run systemctl --user enable xcurs.service
    # restart, not start: picks up an update, and opens a fresh pairing window
    run systemctl --user restart xcurs.service
}

finish() {
    step "Done"
    if ((DRY)); then
        info "(dry run: nothing was changed)"
        return
    fi
    # The service creates the pairing token on first start; wait for it.
    for _ in $(seq 1 50); do
        [[ -s "$TOKEN_FILE" ]] && break
        sleep 0.1
    done
    if ! systemctl --user is-active --quiet xcurs.service; then
        warn "xcurs didn't start. See: journalctl --user -u xcurs -e"
        return
    fi
    cat <<EOF

    xcurs is running and will start by itself at every login.

    ${bold}Now open the xcurs app on your phone (same Wi-Fi) within 2 minutes.${reset}
    It finds this laptop and pairs on its own.

    No app yet? Get it from:
      https://github.com/ayush00git/xcurs/releases/latest
    Or use the touchpad in your phone's browser with this QR code:
EOF
    "$VENV/bin/xcurs" --pair
    cat <<EOF
    Pair another phone later:   systemctl --user restart xcurs
    Logs:                       journalctl --user -u xcurs -f
    Update after a git pull:    ./install.sh
    Remove:                     ./install.sh --uninstall
EOF
}

# ---- uninstall --------------------------------------------------------------

uninstall() {
    step "Removing xcurs"
    run systemctl --user disable --now xcurs.service || true
    run rm -f "$UNIT_DIR/xcurs.service"
    run systemctl --user daemon-reload || true
    run rm -f "$BIN_DIR/xcurs"
    # Only ever delete our own directory.
    if [[ -n "$APP_DIR" && "$APP_DIR" == */xcurs && -d "$APP_DIR" ]]; then
        run rm -rf -- "$APP_DIR"
    fi
    as_root rm -f "$UDEV_RULE" "$MODULES_CONF"
    as_root udevadm control --reload-rules
    info "Kept: your pairing token in $(dirname "$TOKEN_FILE"), and your 'input' group membership."
    info "Firewall rules for port $PORT, if any were added, are also left in place."
}

# ---- main -------------------------------------------------------------------

preflight
if [[ "$MODE" == uninstall ]]; then
    uninstall
    exit 0
fi
install_packages
setup_uinput
install_xcurs
open_firewall
start_service
finish
