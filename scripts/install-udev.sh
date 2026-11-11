#!/bin/sh
# Installs the Helios DAC udev rule so this app can open the DAC without
# root, and applies it to a DAC that is already plugged in (no replug).
#
#   ./install-udev.sh        (asks for your password via sudo)
#
# Run it from the folder it ships in: heliosdac.rules must sit beside it.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
rules="$here/heliosdac.rules"
dest=/etc/udev/rules.d/011_heliosdac.rules

if [ ! -f "$rules" ]; then
    echo "heliosdac.rules not found beside this script ($here)" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Installing the Helios DAC udev rule needs root; asking sudo."
    exec sudo sh "$0" "$@"
fi

install -m 0644 "$rules" "$dest"
echo "Installed $dest"

# The rule is in place; applying it now is a convenience. If udev isn't
# running (container, WSL) say so and carry on: it applies at next boot.
udevadm control --reload-rules \
    || echo "warning: could not reload udev rules (is udev running?)" >&2
udevadm trigger --action=change --subsystem-match=usb \
    --attr-match=idVendor=1209 --attr-match=idProduct=e500 \
    || echo "warning: could not apply the rule to a plugged-in DAC" >&2
udevadm settle || true

# Report what the invoking user can actually do, not just that the DAC is
# present: the rule grants the desktop session and plugdev, so a user on
# SSH outside plugdev still can't open it.
user=${SUDO_USER:-}
found=0
for d in /sys/bus/usb/devices/*; do
    [ "$(cat "$d/idVendor" 2>/dev/null)" = 1209 ] || continue
    [ "$(cat "$d/idProduct" 2>/dev/null)" = e500 ] || continue
    found=1
    node=$(printf '/dev/bus/usb/%03d/%03d' "$(cat "$d/busnum")" "$(cat "$d/devnum")")
    if [ -z "$user" ]; then
        echo "Helios DAC is plugged in ($node)."
    elif su -s /bin/sh "$user" -c "test -r '$node' && test -w '$node'"; then
        echo "Helios DAC is plugged in and $user can open it now. No replug needed."
    else
        echo "Helios DAC is plugged in but $user still can't open $node." >&2
        echo "Over SSH or with no desktop login: sudo usermod -aG plugdev $user," >&2
        echo "then log out and in. At the desktop: unplug and replug the DAC." >&2
    fi
done
[ "$found" = 1 ] || echo "No Helios DAC plugged in right now; the rule applies when you plug one in."
