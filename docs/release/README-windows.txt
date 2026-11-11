Laser! Laser Laser!  (Windows x86-64)
=====================================

A laser visuals synth for the Helios DAC and the LaserCube.
Full manual: https://github.com/edmonkey-nz/laser-laser-laser


1. Run it
---------

Double-click laser-laser-laser.exe.

The app isn't code-signed, so Windows SmartScreen may block it the first
time: click "More info", then "Run anyway".

A small window opens with the address of the control surface
(http://localhost:8080) and a button to open it in your browser.
Everything is controlled from the browser. The Helios DAC library is
included; there is nothing else to install.

Output starts DISARMED with a 5% brightness ceiling. Nothing is emitted
until you choose the output device in Settings and press ARM.
Read the safety notes in the manual before using a real laser.


2. If something goes wrong
--------------------------

- The console window prints what happened. Settings shows why the output
  device couldn't be opened.
- A start-up or crash log is written to error.txt in this folder
  (or %USERPROFILE%\.laserlaserlaser\ if this folder is read-only,
  e.g. under Program Files).
- laser-laser-laser.exe --help lists the command-line options.

Your patterns, masks and settings live in the _internal\ folder
(patterns.json, masks.json, settings.json). Copy them out before
replacing this folder with a newer version.
