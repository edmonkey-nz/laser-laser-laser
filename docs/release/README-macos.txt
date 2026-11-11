Laser! Laser Laser!  (macOS, Apple Silicon)
===========================================

A laser visuals synth for the Helios DAC and the LaserCube.
Full manual: https://github.com/edmonkey-nz/laser-laser-laser


1. Run it
---------

The app isn't code-signed, so macOS Gatekeeper blocks a plain
double-click the first time (it just fails silently). Instead,
right-click laser-laser-laser -> "Open" -> "Open". Or, in Terminal in
this folder:

    xattr -d com.apple.quarantine laser-laser-laser
    ./laser-laser-laser

A small window opens with the address of the control surface
(http://localhost:8080) and a button to open it in your browser.
Everything is controlled from the browser. The Helios DAC library is
included; there is nothing else to install. The first use of the webcam
vectoriser asks for camera permission.

This build is Apple Silicon (M1 and later) only.

Output starts DISARMED with a 5% brightness ceiling. Nothing is emitted
until you choose the output device in Settings and press ARM.
Read the safety notes in the manual before using a real laser.


2. If something goes wrong
--------------------------

- The Terminal window prints what happened. Settings shows why the output
  device couldn't be opened.
- A start-up or crash log is written to error.txt in this folder
  (or ~/.laserlaserlaser/ if this folder is read-only, e.g. in
  /Applications).
- ./laser-laser-laser --help lists the command-line options.

Your patterns, masks and settings live in the _internal/ folder
(patterns.json, masks.json, settings.json). Copy them out before
replacing this folder with a newer version.
