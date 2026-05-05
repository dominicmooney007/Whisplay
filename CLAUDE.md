# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Driver + examples for the **PiSugar Whisplay HAT** (240×280 LCD, RGB LED, single button, WM8960 audio codec). One Python driver targets three different SBCs by auto-detecting the platform at runtime: Raspberry Pi (any model), Radxa ZERO 3W (RK3566), and Radxa Cubie A7Z (Allwinner A733).

## Common commands

Almost everything that touches GPIO/SPI or the audio device requires `sudo`.

```bash
# Install (pick one — must reboot after):
sudo bash Driver/install_wm8960_drive.sh        # Raspberry Pi
sudo bash Driver/install_radxa_zero3w.sh        # Radxa ZERO 3W
sudo bash Driver/install_radxa_cubie_a7z.sh     # Radxa Cubie A7Z

# Smoke test LCD + LED + button + audio:
cd example && sudo bash run_test.sh
# Optionally: sudo bash run_test.sh --image data/test2.jpg --sound data/test.mp3

# Mic loopback (records 10s, plays back):
cd example && sudo bash mic_test.sh

# Other demos (run from example/, all need sudo):
sudo python3 test2.py                           # record/playback state machine
sudo python3 play_mp4.py --file data/whisplay_test.mp4
sudo bash run_record_demo.sh                    # full recording demo with LCD UI
```

There is no test suite, lint config, or build step. The shell wrappers (`run_test.sh`, `run_record_demo.sh`, `mic_test.sh`) exist because the WM8960 ALSA card index is not stable across boots/platforms — they grep `/proc/asound/cards` (or `aplay -l` / `arecord -l`) and pass the resolved index in via `AUDIODEV` / `--card`. Prefer running the wrappers over invoking the Python directly when audio is involved.

Python deps: `pygame Pillow spidev gpiod` (see `example/requirements.txt`). The install scripts apt-install these as `python3-*` packages.

## Architecture

### Single class, multi-platform: `Driver/WhisPlay.py`

`WhisPlayBoard` is the only public class. It owns the LCD (SPI + DC/RST GPIO), the RGB LED (3× software-PWM GPIO), the white backlight LED (PWM or simple on/off depending on hardware), and a polled button. Examples expect to import it as `from WhisPlay import WhisPlayBoard` after `sys.path.append("../Driver")` (or `from Driver.WhisPlay import WhisPlayBoard` from repo root, as `play_mp4.py` does).

The audio codec (WM8960) is **not** managed by this class. It is set up by the install scripts (kernel module, device-tree overlay on Radxa, ALSA config) and driven from userspace via `aplay`/`arecord`/`amixer`/`pygame.mixer`. The driver only checks `/proc/asound/cards` at startup to print a warning if WM8960 isn't present.

### Platform detection and pin maps

`_detect_platform()` reads `/proc/device-tree/model` then falls back to `/proc/device-tree/compatible`, returning `"rpi"`, `"radxa"`, or `"unknown"`. For Radxa, `_detect_radxa_board()` further distinguishes `cubie-a7z` from `zero3w` via the compatible string.

The driver works in **physical (BOARD) pin numbers** (DC=13, RST=7, LED=15, RGB=22/18/16, BUTTON=11). Each platform has its own table mapping BOARD pin → `(gpiochip_number, line_offset)`:

- `_build_rpi_pin_map()` — RPi 5 uses `gpiochip4` (RP1), older Pis use `gpiochip0`; both map to BCM numbers via `_RPI_BOARD_TO_BCM`.
- `RADXA_ZERO3_PIN_MAP` — RK3566 layout.
- `RADXA_CUBIE_A7Z_PIN_MAP` — A733 layout. Note the chip numbering is different here: gpiochip0 covers PA–PK (offsets 0–351), gpiochip1 covers PL–PM.

SPI bus selection is also per-platform: RPi → `/dev/spidev0.0` @ 100 MHz; Radxa ZERO 3W → `spidev3.0` @ 48 MHz; Cubie A7Z → `spidev1.0` @ 48 MHz.

**When adding a new SBC, you need a new pin map, an SPI bus/speed choice in `__init__`, and likely a new install script + DT overlay.**

### gpiod v1 vs v2 compatibility

gpiod has two incompatible Python APIs and the target distros ship a mix. The driver handles both: `_GPIOD_V2 = hasattr(gpiod, 'LineSettings')` switches between `chip.request_lines(config={...})` (v2) and `chip.get_line(...).request(...)` (v1). All call sites go through `_request_output()` / `_request_input()` and the `_LineHandle` wrapper, which exposes a unified `set_value(int)` / `get_value() -> int`. **Don't reach past the wrapper into raw gpiod calls** — anything new should go through `_LineHandle` so it works on both API versions.

### Software PWM

None of the target platforms have usable hardware PWM on these particular pins, so `SoftPWM` runs a Python thread per channel toggling the line at 100 Hz (RGB) or 1 kHz (backlight). Four threads are running in steady state (R, G, B, backlight). Duty cycle is **inverted** for the LEDs because they are common-anode (active LOW): `set_rgb(255,0,0)` calls `ChangeDutyCycle(0)` on red. Same inversion applies to the backlight (`100 - brightness`).

The button is also polled (not interrupt-driven) — a daemon thread reads `BUTTON_PIN` every 10 ms, fires `button_press_callback` / `button_release_callback` on edge. The HAT has an external pull-down, so **pressed = HIGH, released = LOW** (no internal bias needed; `Bias.DISABLED` is requested explicitly).

### LCD

ST7789-style 240×280 panel driven over SPI. The 20-pixel offset baked into `set_window()` (`y0+20, y1+20` for portrait orientations) compensates for the panel's row offset — don't remove it. Pixel format is RGB565 big-endian, two bytes per pixel. Examples convert PIL images to RGB565 by hand (`load_jpg_as_rgb565`). `draw_image()` validates bounds and will raise on overflow. Large frames go through `spi.writebytes2` if available, else chunked `writebytes` (4 KB chunks) — this matters because `play_mp4.py` pushes a full ~134 KB frame per draw.

### Cleanup

Always call `board.cleanup()` on exit (examples do this in a `finally:` block). It stops the four PWM threads, joins the button polling thread, releases gpiod line requests, and closes SPI. Skipping it leaves `/dev/gpiochipN` lines held — the next run will fail with `EBUSY` until process exit.

## ⚠️ Hardware safety

**Radxa Cubie A7Z only:** the physical button on the HAT is wired in a way that's incompatible with the A7Z's power circuitry. **Pressing the button can immediately power off the board.** When testing on A7Z, exercise the button paths with the callback APIs only, not by physically pressing — and call this out in any user-facing docs/examples that target A7Z.
