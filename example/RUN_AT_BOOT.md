# Running a Python Script at Boot (systemd)

This guide walks you through making a Python program start automatically every time your Pi (or Radxa) boots up. We use the `boot_info.py` script in this folder as the working example — it shows the user, hostname, and IP address on the Whisplay LCD as soon as the network is up.

Once you understand the pattern, you can swap in your own script.

---

## What is systemd?

`systemd` is the program on Linux that starts and supervises background services. You give it a small text file (a *unit file*) that describes:

- what to run,
- when to run it,
- what to do if it crashes,
- which user to run it as.

That's it. No scripting, no cron tricks, no `rc.local`.

---

## The example we'll use

**Script:** `boot_info.py`
**Service file:** `whisplay-boot-info.service`

The script needs:

- root privileges (it talks to SPI/GPIO via the Whisplay driver),
- the network to be up (so it can show the IP address),
- the working directory set to `example/` (so the `sys.path.append("../Driver")` line resolves correctly).

The service file below handles all three.

---

## Step 1 — Make sure your script works manually

**Always test by hand before turning it into a service.** A broken service that crash-loops at boot is much harder to debug than a script you can run in a terminal.

```bash
cd /home/dom/Whisplay/example
sudo python3 boot_info.py
```

You should see the LCD light up with **USER**, **HOST**, and **IP**. Press `Ctrl+C` to stop it.

If this doesn't work, fix it before going any further.

---

## Step 2 — Look at the unit file

Open `whisplay-boot-info.service`:

```ini
[Unit]
Description=Whisplay boot info (user + IP) on the LCD
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/dom/Whisplay/example/boot_info.py
WorkingDirectory=/home/dom/Whisplay/example
Restart=on-failure
RestartSec=3
# Needs root for SPI/GPIO/PWM access on the HAT.
User=root

[Install]
WantedBy=multi-user.target
```

Line by line:

| Line | What it does |
|------|--------------|
| `Description=` | Human-readable name shown in `systemctl status` and logs. |
| `After=network-online.target` | Don't start until networking is ready. |
| `Wants=network-online.target` | Ask systemd to actively bring networking up. |
| `Type=simple` | Our script runs in the foreground; systemd treats it as alive while the process is alive. |
| `ExecStart=` | The exact command to run. **Use absolute paths** — systemd has no `$PATH` you can rely on. |
| `WorkingDirectory=` | `cd` into this directory before running. Matters because the script uses a relative import path. |
| `Restart=on-failure` | If the script crashes, restart it. |
| `RestartSec=3` | Wait 3 seconds between restart attempts so we don't hammer a broken script. |
| `User=root` | Run as root. Needed for GPIO/SPI here; **don't use root for things that don't need it**. |
| `WantedBy=multi-user.target` | Start at boot, once the system reaches normal multi-user mode. |

---

## Step 3 — Install the service

systemd looks for unit files in `/etc/systemd/system/`. Copy ours there:

```bash
sudo cp /home/dom/Whisplay/example/whisplay-boot-info.service /etc/systemd/system/
```

Tell systemd to re-scan that directory:

```bash
sudo systemctl daemon-reload
```

---

## Step 4 — Start it now (without rebooting)

```bash
sudo systemctl start whisplay-boot-info
```

Check it's running:

```bash
sudo systemctl status whisplay-boot-info
```

You should see `Active: active (running)` in green. If it says `failed`, jump to **Debugging** below.

---

## Step 5 — Enable it at boot

Starting a service and enabling it are different things:

- `start` runs it right now.
- `enable` makes it run automatically every boot.

```bash
sudo systemctl enable whisplay-boot-info
```

Now reboot to confirm:

```bash
sudo reboot
```

When the Pi comes back, the LCD should show the boot info screen on its own.

---

## Useful commands

```bash
sudo systemctl status whisplay-boot-info     # is it running?
sudo systemctl stop whisplay-boot-info       # stop it (this boot)
sudo systemctl start whisplay-boot-info      # start it (this boot)
sudo systemctl restart whisplay-boot-info    # stop + start
sudo systemctl disable whisplay-boot-info    # don't run at next boot
sudo systemctl enable whisplay-boot-info     # do run at next boot

journalctl -u whisplay-boot-info             # all logs ever
journalctl -u whisplay-boot-info -f          # follow live logs
journalctl -u whisplay-boot-info -b          # only this boot's logs
```

---

## Adapting this for your own script

Copy `whisplay-boot-info.service` to a new name and edit four things:

1. **Filename**: `/etc/systemd/system/my-thing.service`. The bit before `.service` is what you'll use with `systemctl`.
2. **Description**: anything readable.
3. **ExecStart**: the absolute path to `python3` and the absolute path to your script.
4. **WorkingDirectory**: the folder your script expects to be run from.

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now my-thing
```

`--now` is a shortcut for "enable at boot **and** start right now."

### Do you actually need root?

If your script doesn't touch GPIO/SPI/I2C, change `User=root` to `User=dom` (or whatever your account is). Running things as root that don't need to be is bad practice.

For the Whisplay HAT specifically, you do need root because the driver uses `/dev/spidev*` and `/dev/gpiochip*`.

### Do you actually need the network?

If your script doesn't use the network, drop these two lines:

```ini
After=network-online.target
Wants=network-online.target
```

That makes the service start a bit earlier in the boot.

---

## Debugging

**The service won't start.** Read the status output carefully:

```bash
sudo systemctl status whisplay-boot-info
```

Then read the logs:

```bash
journalctl -u whisplay-boot-info -b --no-pager
```

Common causes:

- **Wrong path in `ExecStart`.** systemd doesn't know about `~`, your shell aliases, or `cd`. Every path must be absolute.
- **Script needs a virtualenv.** Point `ExecStart` at the venv's Python: `/home/dom/myenv/bin/python3 /home/dom/myproj/main.py`.
- **Script depends on `$DISPLAY` or login env vars.** Services don't have those. Don't rely on them.
- **GPIO `EBUSY`.** Some other process (or an earlier crashed run that didn't `cleanup()`) is still holding the lines. Reboot or kill the other process.
- **It worked once, then failed forever.** Look for `Restart=` hitting its limit. `systemctl reset-failed whisplay-boot-info` clears the failure counter.

**The LCD shows "waiting for network…" forever.** The script is fine — the network never came up. Check `nmcli` / Wi-Fi config; this is not a systemd problem.

---

## Removing the service

```bash
sudo systemctl disable --now whisplay-boot-info
sudo rm /etc/systemd/system/whisplay-boot-info.service
sudo systemctl daemon-reload
```

---

## Summary

1. Get the script working manually first.
2. Write a `.service` file with absolute paths.
3. Copy it to `/etc/systemd/system/`.
4. `daemon-reload`, `start`, check `status`.
5. `enable` it for next boot.
6. Use `journalctl -u <name> -f` whenever something goes wrong.
