#!/usr/bin/env python3
"""Stop the Whisplay boot-info service for this session.

The boot screen (boot_info.py) holds the LCD, RGB LED, SPI bus, and several
GPIO lines, so other Whisplay programs can't run while it's active. This
script stops it now so you can use the Whisplay for something else; it will
come back automatically on the next reboot.

Run:  sudo python3 disable_bootscreen.py
"""

import os
import subprocess
import sys


SERVICE_NAME = "whisplay-boot-info"
UNIT_PATH = f"/etc/systemd/system/{SERVICE_NAME}.service"


def main():
    if os.geteuid() != 0:
        print(f"error: must be run as root (try: sudo python3 {sys.argv[0]})",
              file=sys.stderr)
        return 1

    if not os.path.exists(UNIT_PATH):
        print(f"{SERVICE_NAME} isn't installed ({UNIT_PATH} not found) — nothing to do.")
        return 0

    is_active = subprocess.run(
        ["systemctl", "is-active", "--quiet", SERVICE_NAME],
        check=False,
    )
    if is_active.returncode != 0:
        print(f"{SERVICE_NAME} is already stopped.")
        return 0

    stop = subprocess.run(
        ["systemctl", "stop", SERVICE_NAME],
        check=False,
        capture_output=True,
        text=True,
    )
    if stop.returncode != 0:
        print(f"error: failed to stop {SERVICE_NAME}", file=sys.stderr)
        if stop.stderr:
            print(stop.stderr.strip(), file=sys.stderr)
        return stop.returncode

    print("Boot screen stopped. The Whisplay is now free to use.")
    print("It will come back automatically on the next reboot.")
    print(f"To stop it permanently, run: sudo systemctl disable {SERVICE_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
