#!/usr/bin/env python3
"""Show the primary login user and IP address on the Whisplay LCD.

Designed to run as a systemd service on boot. Polls every few seconds so
the display updates as network interfaces come up.

Run from /home/dom/Whisplay/example/:  sudo python3 boot_info.py
"""

import argparse
import os
import pwd
import socket
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Driver"))
)
from WhisPlay import WhisPlayBoard  # noqa: E402

WIDTH = 240
HEIGHT = 280


def pil_to_rgb565_bytes(img):
    """Convert a PIL RGB image to RGB565 big-endian bytes."""
    out = bytearray(WIDTH * HEIGHT * 2)
    px = img.load()
    i = 0
    for y in range(HEIGHT):
        for x in range(WIDTH):
            r, g, b = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = (v >> 8) & 0xFF
            out[i + 1] = v & 0xFF
            i += 2
    return bytes(out)


def load_font(size):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def draw_centered(draw, text, font, y, fill):
    tw, _ = text_size(draw, text, font)
    draw.text(((WIDTH - tw) // 2, y), text, fill=fill, font=font)


def primary_login_user():
    """Pick the user to display.

    Prefer SUDO_USER (set when launched via sudo from a real login).
    Fall back to the lowest-UID regular account (UID >= 1000, < 65534).
    """
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        return sudo_user
    candidates = [p for p in pwd.getpwall() if 1000 <= p.pw_uid < 65534]
    if candidates:
        candidates.sort(key=lambda p: p.pw_uid)
        return candidates[0].pw_name
    return os.environ.get("USER") or "unknown"


def get_ip_addresses():
    """Return list of (iface, ip) pairs for non-loopback IPv4 interfaces."""
    results = []
    try:
        out = subprocess.check_output(
            ["ip", "-o", "-4", "addr", "show"], text=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return results
    for line in out.splitlines():
        parts = line.split()
        # Format: "<idx>: <iface>    inet <ip>/<cidr> ..."
        if len(parts) < 4 or parts[2] != "inet":
            continue
        iface = parts[1]
        if iface == "lo":
            continue
        ip = parts[3].split("/", 1)[0]
        results.append((iface, ip))
    return results


def render(user, hostname, ip_pairs):
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 14, 30))
    draw = ImageDraw.Draw(img)

    title_font = load_font(22)
    label_font = load_font(14)
    value_font = load_font(20)
    small_font = load_font(13)

    draw_centered(draw, "Whisplay", title_font, 14, (120, 200, 255))
    draw.line((20, 46, WIDTH - 20, 46), fill=(60, 90, 140))

    y = 64
    draw.text((16, y), "USER", fill=(150, 170, 200), font=label_font)
    draw.text((16, y + 18), user, fill=(255, 255, 255), font=value_font)

    y = 116
    draw.text((16, y), "HOST", fill=(150, 170, 200), font=label_font)
    draw.text((16, y + 18), hostname, fill=(255, 255, 255), font=value_font)

    y = 168
    draw.text((16, y), "IP", fill=(150, 170, 200), font=label_font)
    if not ip_pairs:
        draw.text((16, y + 18), "waiting for network...",
                  fill=(255, 180, 120), font=small_font)
    else:
        for i, (iface, ip) in enumerate(ip_pairs[:3]):
            line_y = y + 18 + i * 22
            draw.text((16, line_y), f"{iface}", fill=(180, 220, 180),
                      font=small_font)
            draw.text((76, line_y), ip, fill=(255, 255, 255), font=value_font)

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    draw_centered(draw, ts, small_font, HEIGHT - 22, (140, 160, 190))
    return img


def main():
    parser = argparse.ArgumentParser(description="Boot info display")
    parser.add_argument("--user", default=None,
                        help="Override the user name shown")
    parser.add_argument("--brightness", type=int, default=80,
                        help="Backlight 0-100 (default 80)")
    parser.add_argument("--interval", type=float, default=3.0,
                        help="Refresh interval in seconds (default 3)")
    args = parser.parse_args()

    user = args.user or primary_login_user()
    hostname = socket.gethostname()

    board = WhisPlayBoard()
    board.set_backlight(max(0, min(100, args.brightness)))
    board.set_rgb(0, 0, 0)

    last_payload = None
    try:
        while True:
            ip_pairs = get_ip_addresses()
            payload = (user, hostname, tuple(ip_pairs),
                       time.strftime("%Y-%m-%d %H:%M"))
            if payload != last_payload:
                img = render(user, hostname, ip_pairs)
                board.draw_image(0, 0, WIDTH, HEIGHT,
                                 pil_to_rgb565_bytes(img))
                board.set_rgb(0, 80, 0) if ip_pairs else board.set_rgb(80, 40, 0)
                last_payload = payload
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
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
