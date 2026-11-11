Laser! Laser Laser!  (Linux x86-64)
===================================

A laser visuals synth for the Helios DAC and the LaserCube.
Full manual: https://github.com/edmonkey-nz/laser-laser-laser


1. ONCE, BEFORE USING A HELIOS DAC: install the USB permission rule
-------------------------------------------------------------------

Without this the app can see the Helios DAC but is not allowed to open
it, and Settings reports "this user can't open it".

Open a terminal in this folder (in the file manager: right-click the
folder background -> "Open in Terminal") and run:

    ./install-udev.sh

It asks for your password, installs the rule and applies it to a DAC
that is already plugged in, so there is no need to replug. Once per
computer: newer versions of the app don't need it again.

If it says "Permission denied", run it as:  sh install-udev.sh

Not using a Helios (LaserCube only, or just the preview)? Skip this.

Also needed: libusb, which most desktops already have. If the Helios
still won't open:  sudo apt install libusb-1.0-0


2. Run it
---------

    ./laser-laser-laser

A small window opens with the address of the control surface
(http://localhost:8080) and a button to open it in your browser.
Everything is controlled from the browser.

Output starts DISARMED with a 5% brightness ceiling. Nothing is emitted
until you choose the output device in Settings and press ARM.
Read the safety notes in the manual before using a real laser.


3. If something goes wrong
--------------------------

- The console prints what happened. Settings shows why the output device
  couldn't be opened, and what to do about it.
- A start-up or crash log is written to error.txt in this folder
  (or ~/.laserlaserlaser/ if this folder is read-only).
- ./laser-laser-laser --help lists the command-line options.

Your patterns, masks and settings live in the _internal/ folder
(patterns.json, masks.json, settings.json). Copy them out before
replacing this folder with a newer version.
