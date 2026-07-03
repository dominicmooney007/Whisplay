# Getting Started with the PiSugar Whisplay HAT

A hands-on guide for students. By the end you'll be able to draw to the screen,
play sounds, record from the microphone, blink the RGB LED, and read the button —
then combine them into a small app.

> **Quick fact-check before we start:** the Whisplay screen is a **1.69" IPS LCD**
> (driver chip ST7789P3), **not** an OLED. It's a full-colour 240×280 display driven
> over SPI. Everything below assumes that LCD.

---

## 1. What is the Whisplay HAT?

The Whisplay HAT is an add-on board ("HAT") that snaps onto a Raspberry Pi Zero /
Zero 2 W / Pi 5 (and some Radxa boards) using the 40-pin header. It packs a screen,
audio, a light, and a button onto one small board so you can build talk-and-see
projects like AI chatbots.

| Feature | Spec | How it connects |
|---|---|---|
| **Screen** | 1.69" IPS LCD, **240×280** px, full colour (RGB565) | SPI |
| **Audio codec** | WM8960 (hi-fi) | I2C (control) + I2S (audio) |
| **Microphone** | Dual mics (stereo) | via WM8960 / I2S |
| **Speaker** | Onboard speaker + external speaker support | via WM8960 / I2S |
| **RGB LED** | One programmable colour LED | GPIO (software PWM) |
| **Button** | One programmable push button | GPIO |
| **Backlight** | Adjustable screen brightness | GPIO (software PWM) |

The three buses matter later for troubleshooting: **SPI** drives the LCD, and **I2C +
I2S** drive the audio. The installer enables all of them for you.

---

## 2. One-time setup

Do this once per Pi. All the hardware demos need to run as **root** (`sudo`) because
they talk directly to GPIO and SPI.

```bash
# 1. Get the code and install the driver (enables SPI, I2C, I2S)
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay
sudo bash install_driver.sh
sudo reboot            # reboot is required for the bus changes to take effect

# 2. Install the Python libraries used by the examples
cd example
pip install -r requirements.txt --break-system-packages
#   pulls in: pygame, Pillow, spidev, gpiod
```

**Check the audio card is present** after reboot — you should see a card named
`whisplaysound` (older boards may show `wm8960` or `es8389`):

```bash
aplay -l                 # lists playback devices
cat /proc/asound/cards   # the Whisplay card should be here
```

If you don't see it, re-run the installer and check the wiring — the audio won't
work until this card appears.

---

## 3. Connecting to the hardware (read this first)

There are **two ways** your program can control the board, and only one program can
own the hardware at a time:

1. **Direct mode** — your script talks straight to the LCD/GPIO. Simplest for
   learning. Use when nothing else is running the screen.
2. **Daemon mode** — a background service (`whisplay-daemon`) owns the hardware and
   your app draws through it. Used when you want an app launcher, or several apps
   sharing the board (covered in §10).

The good news: **the same helper works for both.** `create_whisplay_hardware(...)`
returns a daemon client if the daemon is running, otherwise it falls back to direct
hardware. The methods (`draw_image`, `set_rgb`, `on_button_press`, …) are identical
either way, so the code you learn here is portable.

For the plain "just talk to the hardware" learning path you can also import the board
class directly:

```python
from whisplay import WhisplayBoard   # runtime/whisplay.py
board = WhisplayBoard()              # grabs the LCD, LED, button, backlight
# ... use it ...
board.cleanup()                      # ALWAYS release the hardware when done
```

All examples below assume you have a `board` object from one of those two calls.

---

## 4. The screen — how displaying works

### 4.1 The key idea: colours are RGB565

The LCD stores each pixel as a **16-bit number** (not the 24-bit `#RRGGBB` you may
know from the web). This format is called **RGB565**: 5 bits red, 6 bits green, 5
bits blue. You convert a normal (r, g, b) triple (0–255 each) like this:

```python
def to_rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

RED   = 0xF800   # to_rgb565(255, 0, 0)
GREEN = 0x07E0   # to_rgb565(0, 255, 0)
BLUE  = 0x001F   # to_rgb565(0, 0, 255)
WHITE = 0xFFFF
BLACK = 0x0000
```

### 4.2 The simplest drawing calls

```python
board.fill_screen(RED)            # fill the whole 240x280 screen with one colour
board.draw_pixel(120, 140, WHITE) # one pixel (x from 0..239, y from 0..279)
board.draw_line(0, 0, 239, 279, GREEN)   # a line between two points
```

- `x` runs **0 → 239** (width = 240), `y` runs **0 → 279** (height = 280).
- These live on `board.LCD_WIDTH` and `board.LCD_HEIGHT` if you'd rather not hard-code.

`draw_pixel` and `draw_line` are handy but **slow** (one SPI round-trip per pixel).
For anything real — text, images, shapes — draw into an image first, then push the
whole image at once (next section).

### 4.3 Displaying text and images with Pillow (the normal way)

You build a picture with **Pillow (PIL)**, convert it to RGB565 bytes, and blit the
whole frame with `draw_image`. This is how every real Whisplay app draws.

```python
from PIL import Image, ImageDraw, ImageFont

W, H = board.LCD_WIDTH, board.LCD_HEIGHT   # 240 x 280

def image_to_rgb565(img):
    """Convert a PIL RGB image to the bytes the LCD wants."""
    rgb = img.convert("RGB")
    out = bytearray()
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = rgb.getpixel((x, y))
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out.append((v >> 8) & 0xFF)   # high byte first (big-endian)
            out.append(v & 0xFF)
    return bytes(out)

# Draw "Hello!" in white on a dark blue background
img  = Image.new("RGB", (W, H), (11, 16, 24))
draw = ImageDraw.Draw(img)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
draw.text((30, 120), "Hello!", fill=(255, 255, 255), font=font)

board.draw_image(0, 0, W, H, image_to_rgb565(img))
```

`draw_image(x, y, width, height, pixel_data)` writes a block of RGB565 bytes to a
rectangle. To replace the whole screen, use `x=0, y=0, width=240, height=280`. The
pixel data must be exactly `width × height × 2` bytes or you'll get an error.

**Showing a photo** is the same idea — open it, resize to the screen, convert, blit:

```python
photo = Image.open("cat.png").resize((W, H))
board.draw_image(0, 0, W, H, image_to_rgb565(photo))
```

> **Speed tip:** the pixel-by-pixel `image_to_rgb565` above is easy to read but slow.
> In daemon mode there's a fast built-in `image_to_rgb565_bytes(img)` in
> `daemon/daemon_shared.py`. For direct-mode animation, convert with NumPy instead of
> a Python loop.

---

## 5. Playing sounds through the speaker

Audio does **not** go through the `board` object — it goes through the **WM8960 sound
card** using standard Linux ALSA tools (`aplay` to play, `arecord` to record). Your
Python code just runs those tools.

> **⚠️ Find your card index first.** The `-c 1` / `plughw:1` in the audio examples
> below is only a placeholder — the Whisplay card's number **varies by machine** (on a
> Raspberry Pi 5 it's often **2**, not 1). Check yours with `aplay -l` or
> `cat /proc/asound/cards` and use that number. Easiest of all: pass `-D whisplaysound`
> to `aplay`/`arecord` instead of a numeric device, and you never have to care about the
> index.

### 5.1 Set the volume once (mixer)

The codec starts muted/quiet. Turn up the speaker and mic (replace `1` with your
card index — see the note above):

```bash
amixer -c 1 sset 'Speaker' 121
amixer -c 1 sset 'Playback' 230
amixer -c 1 sset 'Left Output Mixer PCM' on
amixer -c 1 sset 'Right Output Mixer PCM' on
```

### 5.2 Play a WAV file

From the terminal:

```bash
aplay -D whisplaysound test.wav      # newer boards
# or, using the card name from /proc/asound/cards:
aplay -D plughw:CARD=whisplaysound test.wav
```

From Python (this is exactly the pattern the official test uses):

```python
import subprocess

def play_wav(path, device="whisplaysound"):
    subprocess.run(["aplay", "-D", device, path], check=False)

play_wav("test.wav")
```

If `whisplaysound` doesn't work, fall back to `plughw:<card_index>` (e.g.
`plughw:1`). The demos try `whisplaysound` first, then `default`, then `plughw:`.

---

## 6. Recording from the microphone

Recording uses `arecord`. The Whisplay has **dual mics**, so record in stereo at
48 kHz, 16-bit — the codec's native format:

```bash
arecord -D whisplaysound -f S16_LE -r 48000 -c 2 -t wav -d 5 my_recording.wav
#         device          16-bit    48kHz   stereo  wav  5 seconds  output file
```

Boost the mic first if it's too quiet:

```bash
amixer -c 1 sset 'Capture' 45
amixer -c 1 sset 'ADC PCM' 195
amixer -c 1 sset 'Left Input Mixer Boost'  on
amixer -c 1 sset 'Right Input Mixer Boost' on
```

**Record-then-play-back in Python** (a classic "did the mic work?" loop):

```python
import subprocess

DEV = "whisplaysound"

# Record 5 seconds
subprocess.run(["arecord", "-D", DEV, "-f", "S16_LE", "-r", "48000",
                "-c", "2", "-t", "wav", "-d", "5", "clip.wav"], check=False)

# Play it back
subprocess.run(["aplay", "-D", DEV, "clip.wav"], check=False)
```

A common interactive pattern is **hold-the-button to record, release to stop** —
start `arecord` on button-press and send it `SIGINT` on release (see
`example/test.py` for the full version).

---

## 7. The RGB LED

One LED, any colour. Values are 0–255 per channel, just like normal RGB.

```python
board.set_rgb(255, 0, 0)     # red
board.set_rgb(0, 255, 0)     # green
board.set_rgb(0, 0, 255)     # blue
board.set_rgb(255, 255, 255) # white
board.set_rgb(0, 0, 0)       # off

# Smoothly fade to a colour over 500 ms
board.set_rgb_fade(0, 180, 255, duration_ms=500)
```

Great for status: e.g. green = ready, red = recording, blue = thinking.

---

## 8. The button

There's **one** push button. You can react to it two ways.

**Event callbacks** (recommended — runs in the background):

```python
def on_press():
    print("pressed!")
    board.set_rgb(0, 180, 255)

def on_release():
    print("released!")
    board.set_rgb(0, 0, 0)

board.on_button_press(on_press)
board.on_button_release(on_release)
```

**Polling** (check the state yourself in a loop):

```python
if board.button_pressed():
    print("the button is down right now")
```

---

## 9. The backlight

Control screen brightness from 0 (off) to 100 (full):

```python
board.set_backlight(70)   # 70% brightness
board.set_backlight(0)    # screen dark (backlight off)
board.set_backlight(100)  # brightest
```

Turning the backlight down is a nice way to save power when the screen isn't needed.

---

## 10. Putting it together: a tiny app

This shows the screen, LED, and button working together. Save as `hello_whisplay.py`
and run with `sudo python3 hello_whisplay.py` from the `example/` folder.

```python
import os, sys, time
from PIL import Image, ImageDraw, ImageFont

# make runtime/ importable
RUNTIME = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime"))
sys.path.append(RUNTIME)
from whisplay_client import create_whisplay_hardware

board = create_whisplay_hardware(app_id="hello", display_name="Hello", icon="H")
W, H = board.LCD_WIDTH, board.LCD_HEIGHT
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
presses = 0

def to565(img):
    rgb = img.convert("RGB"); out = bytearray()
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = rgb.getpixel((x, y))
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out += bytes([(v >> 8) & 0xFF, v & 0xFF])
    return bytes(out)

def show(text):
    img = Image.new("RGB", (W, H), (11, 16, 24))
    ImageDraw.Draw(img).text((24, 120), text, fill=(255, 255, 255), font=font)
    board.draw_image(0, 0, W, H, to565(img))

def pressed():
    global presses
    presses += 1
    board.set_rgb(0, 200, 120)
    show(f"Presses: {presses}")

def released():
    board.set_rgb(0, 0, 0)

board.set_backlight(80)
board.on_button_press(pressed)
board.on_button_release(released)
show("Press the button!")

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    board.cleanup()   # always clean up!
```

Try the ready-made demos too, all in `example/` (run with `sudo`):

```bash
cd example
sudo bash run_test.sh          # full guided screen/LED/speaker/button/mic test
sudo python3 flappy_bird.py    # one-button game
sudo python3 jump_game.py      # one-button game
sudo python3 play_mp4.py --file data/whisplay_test.mp4   # play video (needs ffmpeg)
```

---

## 11. Bonus: the Whisplay Daemon (app launcher)

Once you're comfortable, the **daemon** turns the HAT into a little app console. It
owns the hardware and shows a desktop of apps you can switch between with the button.

```bash
sudo bash daemon/install_whisplay_daemon_service.sh
systemctl status whisplay-daemon.service --no-pager
```

Desktop gestures: **single-click** cycles the selected app, **long-press** launches
it, and **4 quick clicks** exit back to the desktop. It even has built-in **Bluetooth,
Wi-Fi, and Volume** pages.

To make your own app show up on the desktop, register it and drop a small JSON file
in `~/.whisplay-daemon/app/`. Because `create_whisplay_hardware()` already speaks the
daemon protocol, **your app code barely changes** — you just also register callbacks
for `on_exit_request` (user asked to quit) and `on_focus_revoked` (daemon took the
screen back):

```python
if hasattr(board, "on_exit_request"):
    board.on_exit_request(lambda *_: stop())
if hasattr(board, "on_focus_revoked"):
    board.on_focus_revoked(lambda *_: stop())
```

Full details: `APP_INTEGRATION.md` and `daemon/skills/create-app/SKILL.md` in this
repo.

---

## 12. Troubleshooting

| Problem | Likely cause / fix |
|---|---|
| Screen stays black | Backlight at 0 — call `board.set_backlight(80)`. Also confirm you ran the driver installer + rebooted. |
| `Permission denied` / GPIO errors | Run with `sudo`. Direct hardware access needs root. |
| Only one program can use the screen | The daemon may be running and holding the hardware. Stop it (`sudo systemctl stop whisplay-daemon`) for direct-mode scripts. |
| No sound / no card | Check `cat /proc/asound/cards` for `whisplaysound`. Re-run the installer. Turn up the mixer (§5.1). |
| Sound too quiet | Raise `Speaker`/`Playback` (playback) or `Capture`/`ADC PCM` (record) with `amixer`. |
| `aplay: device ... not found` | Use your real card index: `aplay -D plughw:1 file.wav`. |
| Colours look wrong | You probably sent 24-bit RGB — the LCD needs **RGB565** (§4.1). |
| Image "exceeds screen bounds" error | Your `draw_image` region is bigger than 240×280, or the byte count ≠ `w×h×2`. |

> ⚠️ **Radxa Cubie A7Z owners:** do **not** press the physical button on that board —
> a circuit incompatibility can cut power instantly. (Raspberry Pi is fine.)

---

## 13. Quick API reference (`board` object)

| Call | What it does |
|---|---|
| `fill_screen(color565)` | Fill the whole screen with one RGB565 colour |
| `draw_pixel(x, y, color565)` | Set one pixel (slow) |
| `draw_line(x0, y0, x1, y1, color565)` | Draw a line (slow) |
| `draw_image(x, y, w, h, rgb565_bytes)` | Blit a block of pixels (the fast, normal way) |
| `set_backlight(0–100)` | Screen brightness |
| `set_rgb(r, g, b)` | LED colour, 0–255 each |
| `set_rgb_fade(r, g, b, duration_ms)` | Smoothly fade the LED |
| `button_pressed()` | `True` if the button is down now |
| `on_button_press(fn)` / `on_button_release(fn)` | Button event callbacks |
| `on_exit_request(fn)` / `on_focus_revoked(fn)` | Daemon-mode lifecycle callbacks |
| `cleanup()` | Release the hardware — always call when finished |
| `LCD_WIDTH` (240) / `LCD_HEIGHT` (280) | Screen size constants |

Audio is separate: use `aplay` (play) and `arecord` (record) on the `whisplaysound`
ALSA card, and `amixer` to set levels.

---

## Sources

- [Whisplay HAT — PiSugar Docs (intro)](https://docs.pisugar.com/docs/product-wiki/whisplay/intro)
- [Product Overview — PiSugar Docs](https://docs.pisugar.com/docs/product-wiki/whisplay/overview)
- [Whisplay HAT product page — PiSugar](https://www.pisugar.com/products/whisplay-hat-for-pi-zero-2w-audio-display)
- [PiSugar/Whisplay — GitHub](https://github.com/PiSugar/whisplay)
- This repository's own code: `runtime/whisplay.py`, `runtime/whisplay_client.py`, `example/test.py`, `daemon/skills/create-app/SKILL.md`
