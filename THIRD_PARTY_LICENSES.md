# Third-Party Licenses

Laser! Laser Laser! ("the project") is licensed under the MIT License
(see `LICENSE`). It depends on and/or bundles the following third-party
components, each under its own license. All are permissive licenses
compatible with distributing this project under MIT.

## Bundled binary

**libHeliosDacAPI.so** — compiled from the Helios DAC SDK host driver
(`sdk/` folder of github.com/Grix/helios_dac), **MIT License**, © Gitle
Mikkelsen. The SDK's host software/driver is explicitly MIT-licensed and
free for any use including commercial. Note: only the *host driver* is
bundled here; the Helios firmware and hardware designs (not included in
this project) carry an MIT + Commons Clause (non-commercial) license — if
you rebuild the `.so`, you only compile the MIT-licensed `sdk/cpp` code.

Rebuild instructions are in the README. The SDK links against **libusb**
(LGPL-2.1), which is dynamically loaded from your system, not bundled.

## Python dependencies (installed via pip, not bundled)

| Package                 | License        |
|-------------------------|----------------|
| numpy                   | BSD-3-Clause   |
| mido                    | MIT            |
| python-rtmidi           | MIT            |
| sounddevice             | MIT            |
| pygame                  | LGPL-2.1       |
| aiohttp                 | Apache-2.0     |
| opencv-python-headless  | Apache-2.0     |

**pygame** is LGPL-2.1. This project imports it as an unmodified library
(dynamic linking), which LGPL permits in an MIT-licensed application. If
you distribute a bundled binary (e.g. a PyInstaller build) that includes
pygame, keep it as a replaceable shared library and include pygame's
license text to satisfy the LGPL — see pygame's documentation for the
current guidance.

None of these packages are redistributed in this repository; they are
listed in `requirements.txt` and fetched by pip at install time.

## Fonts / assets

The UI uses the browser's built-in monospace fonts (no bundled fonts).

The app icon (`icon.png`, also used as the favicon): Sine icon created by
Grand Iconic — Flaticon (https://www.flaticon.com/).
