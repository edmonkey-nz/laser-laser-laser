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
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=1209
udevadm settle || true
echo "Installed $dest"

if command -v lsusb >/dev/null 2>&1 && lsusb -d 1209:e500 >/dev/null 2>&1; then
    echo "Helios DAC is plugged in; access applied now. No replug needed."
else
    echo "No Helios DAC plugged in right now; the rule applies when you plug one in."
fi
