#!/usr/bin/env python3
"""Whisplay multi-scene graphics demo.

Cycles through a title card, plasma, bouncing balls, warp starfield, and
fireworks. Press the on-board button to skip to the next scene. The RGB LED
fades to a colour that matches the active scene. An FPS counter is overlaid
in the top-right.

Run from /home/dom/Whisplay/example/ with:  sudo python3 fun_demo.py
"""

import argparse
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
        "numpy is required. Install it with: sudo apt install python3-numpy\n"
    )
    sys.exit(1)

from PIL import Image, ImageDraw, ImageFont

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Driver"))
)
from WhisPlay import WhisPlayBoard  # noqa: E402

WIDTH = 240
HEIGHT = 280
# Bump to 2 if FPS dips too low — renders the heavy scene at half-res then
# nearest-neighbour upscales for the SPI push.
RES_DIVISOR = 1


# ---------- shared helpers ----------

def pil_to_rgb565_bytes(img):
    """Convert a PIL RGB image to a big-endian RGB565 byte buffer."""
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT))
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


# ---------- scenes ----------

class Scene:
    name = "scene"
    led_color = (128, 128, 128)
    duration = None  # None = run until the user presses the button

    def __init__(self):
        self.t0 = time.monotonic()

    def elapsed(self):
        return time.monotonic() - self.t0

    def render(self, t, dt):
        raise NotImplementedError


class TitleScene(Scene):
    name = "title"
    led_color = (220, 220, 220)
    duration = 2.4

    def __init__(self):
        super().__init__()
        self.font_big = load_font(40)
        self.font_sub = load_font(14)

    def render(self, t, dt):
        e = self.elapsed()
        rows = np.linspace(0.0, 1.0, HEIGHT, dtype=np.float32)[:, None]
        cols = np.linspace(0.0, 1.0, WIDTH, dtype=np.float32)[None, :]
        phase = e * 1.2
        r = (np.sin(rows * 3.0 + phase) * 0.5 + 0.5) * 90.0
        g = (np.sin(cols * 4.0 + phase * 1.3) * 0.5 + 0.5) * 70.0
        b = (np.sin((rows + cols) * 5.0 + phase * 0.7) * 0.5 + 0.5) * 220.0
        r_full = np.broadcast_to(r, (HEIGHT, WIDTH))
        g_full = np.broadcast_to(g, (HEIGHT, WIDTH))
        bg = np.stack([r_full, g_full, b], axis=-1).astype(np.uint8)
        img = Image.fromarray(bg, "RGB")
        draw = ImageDraw.Draw(img)

        text = "WHISPLAY"
        tw, th = text_size(draw, text, self.font_big)
        bounce = int(6 * math.sin(e * 7.0))
        x = (WIDTH - tw) // 2
        y = (HEIGHT - th) // 2 - 10 + bounce
        draw.text((x + 3, y + 3), text, fill=(0, 0, 0), font=self.font_big)
        draw.text((x, y), text, fill=(255, 255, 255), font=self.font_big)

        sub = "graphics demo"
        sw, _ = text_size(draw, sub, self.font_sub)
        draw.text(((WIDTH - sw) // 2, y + th + 14), sub,
                  fill=(255, 255, 255), font=self.font_sub)
        return img


class PlasmaScene(Scene):
    name = "plasma"
    led_color = (180, 0, 200)

    def __init__(self):
        super().__init__()
        w = max(1, WIDTH // RES_DIVISOR)
        h = max(1, HEIGHT // RES_DIVISOR)
        self._w = w
        self._h = h
        self._x = np.arange(w, dtype=np.float32)[None, :]
        self._y = np.arange(h, dtype=np.float32)[:, None]
        self._cx = w / 2.0
        self._cy = h / 2.0

    def render(self, t, dt):
        e = self.elapsed()
        x = self._x
        y = self._y
        v = (np.sin(x * 0.07 + e * 1.7)
             + np.sin(y * 0.09 + e * 1.3)
             + np.sin((x + y) * 0.05 + e)
             + np.sin(np.sqrt((x - self._cx) ** 2 + (y - self._cy) ** 2)
                      * 0.06 + e * 2.1))
        h = ((v / 4.0) + e * 0.05) % 1.0
        hsv = np.empty((self._h, self._w, 3), dtype=np.uint8)
        hsv[..., 0] = (h * 255).astype(np.uint8)
        hsv[..., 1] = 220
        hsv[..., 2] = 240
        img = Image.fromarray(hsv, "HSV").convert("RGB")
        if (self._w, self._h) != (WIDTH, HEIGHT):
            img = img.resize((WIDTH, HEIGHT), Image.NEAREST)
        return img


class BallsScene(Scene):
    name = "balls"
    led_color = (255, 110, 0)

    def __init__(self):
        super().__init__()
        self.canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        rng = random.Random(7)
        self.balls = []
        for _ in range(8):
            self.balls.append({
                "x": rng.uniform(20, WIDTH - 20),
                "y": rng.uniform(20, HEIGHT - 20),
                "vx": rng.uniform(-110, 110),
                "vy": rng.uniform(-110, 110),
                "r": rng.randint(8, 16),
                "color": (rng.randint(140, 255),
                          rng.randint(140, 255),
                          rng.randint(140, 255)),
            })

    def render(self, t, dt):
        self.canvas = (self.canvas.astype(np.uint16) * 80 // 100).astype(np.uint8)
        img = Image.fromarray(self.canvas, "RGB")
        draw = ImageDraw.Draw(img)
        for b in self.balls:
            b["x"] += b["vx"] * dt
            b["y"] += b["vy"] * dt
            if b["x"] < b["r"]:
                b["x"] = b["r"]; b["vx"] = -b["vx"]
            if b["x"] > WIDTH - b["r"]:
                b["x"] = WIDTH - b["r"]; b["vx"] = -b["vx"]
            if b["y"] < b["r"]:
                b["y"] = b["r"]; b["vy"] = -b["vy"]
            if b["y"] > HEIGHT - b["r"]:
                b["y"] = HEIGHT - b["r"]; b["vy"] = -b["vy"]
            draw.ellipse(
                (b["x"] - b["r"], b["y"] - b["r"],
                 b["x"] + b["r"], b["y"] + b["r"]),
                fill=b["color"],
                outline=(255, 255, 255),
            )
        self.canvas = np.asarray(img, dtype=np.uint8).copy()
        return img


class StarsScene(Scene):
    name = "stars"
    led_color = (40, 90, 255)

    def __init__(self):
        super().__init__()
        self.canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        rng = np.random.default_rng(13)
        n = 140
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
        return img


class FireworksScene(Scene):
    name = "fireworks"
    led_color = (220, 20, 180)

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
        for _ in range(45):
            ang = random.uniform(0, 2 * math.pi)
            spd = random.uniform(35, 115)
            self.particles.append({
                "x": x, "y": y,
                "vx": math.cos(ang) * spd,
                "vy": math.sin(ang) * spd,
                "life": random.uniform(0.8, 1.4),
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
            self._next_launch = e + random.uniform(0.4, 1.1)
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
        return img


# ---------- overlay & main ----------

def overlay_fps(img, fps):
    draw = ImageDraw.Draw(img)
    text = f"{fps:4.1f} fps"
    font = load_font(11)
    tw, _ = text_size(draw, text, font)
    x = WIDTH - tw - 4
    y = 3
    draw.text((x + 1, y + 1), text, fill=(0, 0, 0), font=font)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def main():
    parser = argparse.ArgumentParser(
        description="Whisplay multi-scene graphics demo")
    parser.add_argument("--no-title", action="store_true",
                        help="Skip the title card")
    parser.add_argument("--brightness", type=int, default=80,
                        help="Backlight 0-100 (default 80)")
    args = parser.parse_args()

    board = WhisPlayBoard()
    board.set_backlight(max(0, min(100, args.brightness)))
    board.set_rgb(0, 0, 0)

    main_scenes = [PlasmaScene, BallsScene, StarsScene, FireworksScene]
    scene_index = 0
    advance_event = [False]

    def on_press():
        advance_event[0] = True

    board.on_button_press(on_press)

    using_title = not args.no_title
    if using_title:
        scene = TitleScene()
    else:
        scene = main_scenes[scene_index]()
    board.set_rgb_fade(*scene.led_color, 250)

    last_time = time.monotonic()
    frame_times = deque(maxlen=30)
    fps = 0.0

    print("Demo running. Press the on-board button to cycle scenes. "
          "Ctrl+C to quit.")

    try:
        while True:
            now = time.monotonic()
            dt = max(1e-3, min(0.1, now - last_time))
            last_time = now

            advance = advance_event[0]
            advance_event[0] = False

            next_cls = None
            if using_title and scene.elapsed() >= scene.duration:
                using_title = False
                scene_index = 0
                next_cls = main_scenes[0]
            elif advance:
                if using_title:
                    using_title = False
                    scene_index = 0
                    next_cls = main_scenes[0]
                else:
                    scene_index = (scene_index + 1) % len(main_scenes)
                    next_cls = main_scenes[scene_index]

            if next_cls is not None:
                scene = next_cls()
                board.set_rgb_fade(*scene.led_color, 250)
                last_time = time.monotonic()
                continue

            img = scene.render(now, dt)
            frame_times.append(dt)
            if len(frame_times) >= 5:
                fps = len(frame_times) / sum(frame_times)
            overlay_fps(img, fps)
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
