#!/usr/bin/env bash
# Rebuild libHeliosDacAPI.so from the Helios SDK for your system.
# Use this if the bundled .so won't load (wrong glibc/arch/distro).
#
#   sudo apt install libusb-1.0-0-dev g++ git
#   ./build_helios_lib.sh
#
set -euo pipefail

WORK="$(mktemp -d)"
echo "Cloning Helios SDK into $WORK ..."
git clone --depth 1 https://github.com/Grix/helios_dac.git "$WORK/helios_dac"

cd "$WORK/helios_dac/sdk/cpp/shared_library"
echo "Compiling libHeliosDacAPI.so ..."
g++ -O2 -fPIC -shared -std=c++14 -o libHeliosDacAPI.so \
    HeliosDacAPI.cpp ../HeliosDac.cpp \
    ../idn/idn.cpp ../idn/idnServerList.cpp ../idn/plt-posix.cpp \
    $(pkg-config --cflags --libs libusb-1.0) -I.. -lpthread

DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp libHeliosDacAPI.so "$DEST/"
echo "Done — copied libHeliosDacAPI.so to $DEST"
rm -rf "$WORK"
