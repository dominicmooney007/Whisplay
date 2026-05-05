#!/usr/bin/env python3
"""Whisplay name-card demo for Mr Mooney / STEM Department @ SAS.

Four themed scenes, each prominently displaying the name. Press the on-board
button to cycle scenes. The RGB LED matches each scene's mood.

Run from /home/dom/Whisplay/example/:  sudo python3 mooney_demo.py
"""

import argparse
import colorsys
import math
import os
import random
import sys
import time
from collections import deque

try:
    import numpy as np
except ImportError:
    sys.stderr.write(
        "numpy is required. Install: sudo apt install python3-numpy\n")
    sys.exit(1)

from PIL import Image, ImageDraw, ImageFont

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Driver"))
)
from WhisPlay import WhisPlayBoard  # noqa: E402

WIDTH = 240
HEIGHT = 280
NAME = "Mr Mooney"
SUBTITLE = "STEM Department @ SAS"


# ---------- helpers ----------

def pil_to_rgb565_bytes(img):
    arr = np.asarray(img, dtype=np.uint16)
    r5 = (arr[..., 0] >> 3) & 0x1F
    g6 = (arr[..., 1] >> 2) & 0x3F
    b5 = (arr[..., 2] >> 3) & 0x1F
    rgb565 = (r5 << 11) | (g6 << 5) | b5
    flat = rgb565.flatten()
    out = np.empty(flat.size * 2, dtype=np.uint8)
    out[0::2] = (flat >> 8).astype(np.uint8)
    out[1::2] = (flat & 0xFF).astype(np.uint8)
    return out.tobytes()


_FONT_CACHE = {}

def load_font(size):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    )
    font = None
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def draw_centered(draw, text, font, y, fill, shadow=(0, 0, 0), shadow_off=2):
    tw, _ = text_size(draw, text, font)
    x = (WIDTH - tw) // 2
    if shadow is not None:
        draw.text((x + shadow_off, y + shadow_off), text,
                  fill=shadow, font=font)
    draw.text((x, y), text, fill=fill, font=font)


# ---------- scenes ----------

class Scene:
    name = "scene"
    led_color = (128, 128, 128)
    dynamic_led = False

    def __init__(self):
        self.t0 = time.monotonic()
        self.font_name = load_font(34)
        self.font_sub = load_font(13)

    def elapsed(self):
        return time.monotonic() - self.t0

    def led_for(self, t):
        return self.led_color

    def render(self, t, dt):
        raise NotImplementedError


class RainbowLettersScene(Scene):
    """Each letter of the name cycles through rainbow hues with a wave bob."""
    name = "rainbow"
    led_color = (255, 0, 200)
    dynamic_led = True

    def __init__(self):
        super().__init__()
        self.font_name = load_font(40)

    def led_for(self, t):
        h = (self.elapsed() * 0.4) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
        return (int(r * 255), int(g * 255), int(b * 255))

    def render(self, t, dt):
        e = self.elapsed()
        img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        widths = []
        total = 0
        for ch in NAME:
            cw, _ = text_size(draw, ch, self.font_name)
            widths.append(cw)
            total += cw
        _, name_h = text_size(draw, NAME, self.font_name)
        x = (WIDTH - total) // 2
        y_base = (HEIGHT // 2) - name_h - 4

        for i, ch in enumerate(NAME):
            hue = ((i / max(1, len(NAME))) + e * 0.5) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = (int(r * 255), int(g * 255), int(b * 255))
            bob = int(6 * math.sin(e * 5 + i * 0.7))
            draw.text((x + 2, y_base + bob + 2), ch,
                      fill=(0, 0, 0), font=self.font_name)
            draw.text((x, y_base + bob), ch, fill=color, font=self.font_name)
            x += widths[i]

        sub_y = (HEIGHT // 2) + 18
        draw_centered(draw, SUBTITLE, self.font_sub, sub_y,
                      fill=(230, 230, 230))

        # Sparkles.
        rng = random.Random(int(e * 8))
        for _ in range(14):
            sx = rng.randint(0, WIDTH - 1)
            sy = rng.randint(0, HEIGHT - 1)
            sb = rng.randint(120, 255)
            draw.point((sx, sy), fill=(sb, sb, sb))
        return img


class PlasmaCardScene(Scene):
    """Plasma background, white name in the foreground."""
    name = "plasma"
    led_color = (180, 0, 220)

    def __init__(self):
        super().__init__()
        self._x = np.arange(WIDTH, dtype=np.float32)[None, :]
        self._y = np.arange(HEIGHT, dtype=np.float32)[:, None]

    def render(self, t, dt):
        e = self.elapsed()
        x = self._x
        y = self._y
        v = (np.sin(x * 0.06 + e * 1.5)
             + np.sin(y * 0.08 + e * 1.1)
             + np.sin((x + y) * 0.05 + e)
             + np.sin(np.sqrt((x - WIDTH / 2) ** 2 + (y - HEIGHT / 2) ** 2)
                      * 0.06 + e * 1.8))
        h = ((v / 4.0) + e * 0.04) % 1.0
        hsv = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
        hsv[..., 0] = (h * 255).astype(np.uint8)
        hsv[..., 1] = 200
        hsv[..., 2] = 220
        img = Image.fromarray(hsv, "HSV").convert("RGB")

        draw = ImageDraw.Draw(img)
        _, name_h = text_size(draw, NAME, self.font_name)
        y_name = (HEIGHT // 2) - name_h
        draw_centered(draw, NAME, self.font_name, y_name,
                      fill=(255, 255, 255), shadow=(0, 0, 0), shadow_off=3)
        draw_centered(draw, SUBTITLE, self.font_sub,
                      y_name + name_h + 12,
                      fill=(255, 255, 255), shadow=(0, 0, 0), shadow_off=2)
        return img


class StarfieldCardScene(Scene):
    """Warp-speed stars zoom past the name."""
    name = "stars"
    led_color = (40, 120, 255)

    def __init__(self):
        super().__init__()
        self.canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        rng = np.random.default_rng(21)
        n = 130
        self.x = rng.uniform(-1.0, 1.0, n).astype(np.float32)
        self.y = rng.uniform(-1.0, 1.0, n).astype(np.float32)
        self.z = rng.uniform(0.1, 1.0, n).astype(np.float32)
        self.prev_sx = np.full(n, WIDTH / 2.0, dtype=np.float32)
        self.prev_sy = np.full(n, HEIGHT / 2.0, dtype=np.float32)
        self._first = True
        self._rng = rng

    def render(self, t, dt):
        self.canvas = (self.canvas.astype(np.uint16) * 70 // 100).astype(np.uint8)
        img = Image.fromarray(self.canvas, "RGB")
        draw = ImageDraw.Draw(img)
        cx, cy = WIDTH / 2.0, HEIGHT / 2.0
        self.z -= 0.55 * dt
        respawn = self.z <= 0.05
        if respawn.any():
            n = int(respawn.sum())
            self.x[respawn] = self._rng.uniform(-1.0, 1.0, n).astype(np.float32)
            self.y[respawn] = self._rng.uniform(-1.0, 1.0, n).astype(np.float32)
            self.z[respawn] = 1.0
            self.prev_sx[respawn] = cx
            self.prev_sy[respawn] = cy
        sx = cx + (self.x / self.z) * cx
        sy = cy + (self.y / self.z) * cy
        if self._first:
            self.prev_sx[:] = sx
            self.prev_sy[:] = sy
            self._first = False
        bright = np.clip((1.0 - self.z) * 255.0, 60, 255).astype(np.uint8)
        for i in range(self.z.size):
            if 0 <= sx[i] < WIDTH and 0 <= sy[i] < HEIGHT:
                v = int(bright[i])
                draw.line(
                    (float(self.prev_sx[i]), float(self.prev_sy[i]),
                     float(sx[i]), float(sy[i])),
                    fill=(v, v, v), width=1,
                )
        self.prev_sx[:] = sx
        self.prev_sy[:] = sy
        self.canvas = np.asarray(img, dtype=np.uint8).copy()

        # Overlay text in cyan-edged white.
        _, name_h = text_size(draw, NAME, self.font_name)
        y_name = (HEIGHT // 2) - name_h
        draw_centered(draw, NAME, self.font_name, y_name,
                      fill=(255, 255, 255), shadow=(0, 100, 200), shadow_off=2)
        draw_centered(draw, SUBTITLE, self.font_sub,
                      y_name + name_h + 12,
                      fill=(180, 220, 255), shadow=(0, 0, 0), shadow_off=1)
        return img


class FireworksCardScene(Scene):
    """Fireworks bursting behind the name."""
    name = "fireworks"
    led_color = (220, 60, 180)

    def __init__(self):
        super().__init__()
        self.canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        self.rockets = []
        self.particles = []
        self._next_launch = 0.0

    def _launch(self):
        self.rockets.append({
            "x": random.uniform(40, WIDTH - 40),
            "y": HEIGHT - 4.0,
            "vy": random.uniform(-220, -170),
            "color": (random.randint(180, 255),
                      random.randint(180, 255),
                      random.randint(180, 255)),
        })

    def _burst(self, x, y, color):
        for _ in range(40):
            ang = random.uniform(0, 2 * math.pi)
            spd = random.uniform(35, 110)
            self.particles.append({
                "x": x, "y": y,
                "vx": math.cos(ang) * spd,
                "vy": math.sin(ang) * spd,
                "life": random.uniform(0.8, 1.3),
                "age": 0.0,
                "color": color,
            })

    def render(self, t, dt):
        self.canvas = (self.canvas.astype(np.uint16) * 78 // 100).astype(np.uint8)
        img = Image.fromarray(self.canvas, "RGB")
        draw = ImageDraw.Draw(img)
        e = self.elapsed()
        if e >= self._next_launch and len(self.rockets) < 3:
            self._launch()
            self._next_launch = e + random.uniform(0.4, 1.0)
        gravity = 90.0
        for r in list(self.rockets):
            r["vy"] += gravity * dt
            r["y"] += r["vy"] * dt
            draw.ellipse((r["x"] - 2, r["y"] - 2, r["x"] + 2, r["y"] + 2),
                         fill=r["color"])
            if r["vy"] >= -25:
                self._burst(r["x"], r["y"], r["color"])
                self.rockets.remove(r)
        for p in list(self.particles):
            p["age"] += dt
            if p["age"] >= p["life"]:
                self.particles.remove(p)
                continue
            p["vy"] += gravity * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            k = max(0.0, 1.0 - p["age"] / p["life"])
            col = (int(p["color"][0] * k),
                   int(p["color"][1] * k),
                   int(p["color"][2] * k))
            draw.ellipse((p["x"] - 1, p["y"] - 1, p["x"] + 1, p["y"] + 1),
                         fill=col)
        self.canvas = np.asarray(img, dtype=np.uint8).copy()

        # Foreground name.
        _, name_h = text_size(draw, NAME, self.font_name)
        y_name = (HEIGHT // 2) - name_h
        draw_centered(draw, NAME, self.font_name, y_name,
                      fill=(255, 240, 180), shadow=(0, 0, 0), shadow_off=3)
        draw_centered(draw, SUBTITLE, self.font_sub,
                      y_name + name_h + 12,
                      fill=(255, 220, 200), shadow=(0, 0, 0), shadow_off=1)
        return img


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description="Mr Mooney name-card demo")
    parser.add_argument("--brightness", type=int, default=80,
                        help="Backlight 0-100 (default 80)")
    parser.add_argument("--start", type=int, default=0,
                        help="Start scene index (0-3)")
    args = parser.parse_args()

    scenes = [RainbowLettersScene, PlasmaCardScene,
              StarfieldCardScene, FireworksCardScene]

    board = WhisPlayBoard()
    board.set_backlight(max(0, min(100, args.brightness)))
    board.set_rgb(0, 0, 0)

    scene_index = max(0, min(len(scenes) - 1, args.start))
    advance_event = [False]

    def on_press():
        advance_event[0] = True

    board.on_button_press(on_press)

    scene = scenes[scene_index]()
    board.set_rgb_fade(*scene.led_color, 250)

    last_time = time.monotonic()
    print(f"Showing: {NAME} | {SUBTITLE}")
    print("Press the on-board button to cycle scenes. Ctrl+C to quit.")

    try:
        while True:
            now = time.monotonic()
            dt = max(1e-3, min(0.1, now - last_time))
            last_time = now

            if advance_event[0]:
                advance_event[0] = False
                scene_index = (scene_index + 1) % len(scenes)
                scene = scenes[scene_index]()
                board.set_rgb_fade(*scene.led_color, 250)
                last_time = time.monotonic()
                continue

            img = scene.render(now, dt)
            if scene.dynamic_led:
                board.set_rgb(*scene.led_for(now))
            board.draw_image(0, 0, WIDTH, HEIGHT, pil_to_rgb565_bytes(img))
    except KeyboardInterrupt:
        print("\nExiting demo.")
    finally:
        try:
            board.fill_screen(0x0000)
        except Exception:
            pass
        try:
            board.set_rgb(0, 0, 0)
        except Exception:
            pass
        board.cleanup()


if __name__ == "__main__":
    main()
