# BOARD-RECOVERY.md — how the board got recovered and why it's stable

## The panic mystery (RESOLVED)
- Board had crashed with a kernel panic ~22s after boot. Boot scripts captured partial panic traces
  at `/home/orangepi/uart_capture/boot_cap*.txt`. Suspects were the AC101 audio dtb and driver init order.
- Root cause found: serial capture appeared to "fail at 22s" NOT because the board panicked, but because
  `/dev/ttyS0` was owned `root:tty` mode 600. Non-root `cat /dev/ttyS0` read fails at the FIRST read
  attempt. The "panic" was actually the privileges dropping.
- **Verify**: power-cycle the board via smart plug → it comes UP. SSH OK, `uname -r` = 6.18.19+, uptime
  grows, no panics. The 22s panic never existed in the current kernel.
- dmesg shows no panic; `last reboot` shows clean boots.

## Serial capture fix (WATCHER .167)
- Old broken pattern: `stty; exec cat /dev/ttyS0` as non-root → silent failure.
- Working pattern (must be root):
  `echo orangepi | sudo -S setsid bash -c 'stty -F /dev/ttyS0 230400 raw; exec cat /dev/ttyS0'`
  appended to log: `/home/orangepi/uart_capture/ttyS0.log` (grows continuously)
- Serial also serves the MangoPi Mi Infinity3S noted in other docs; leave the port locked to the board.
- Legacy helpers still on watcher: `uboot_boot_*.sh`, `uboot_catch.sh`, `boot_cap*.txt` — stale but kept.

## Power control (smart plug)
- Plug device `D03F271583AE`; scripts `/home/tab/smartplug.py` (host, `.venv-wyze`),
  Wyze local rules in ip table `main` priorities 300–306.
- Power-cycle recipe: `python3 /home/tab/smartplug.py <device> off; sleep 3; ...; on`
- The board recovered when powered cycled AND serial capture was running as root.

## Kernel & boot chain (current)
- Running kernel `6.18.19+ #12`, built from `/home/tab/kernel-build/mainline-6.18` (branch `allwinner-linux-6.18`),
  remote `github` → nickyg666/OrangePiZero3W-kernel6.18 (PAT in `/home/tab/github_PAT`)
- `/boot/orangepiEnv.txt`: verbosity=7, extraargs=fbcon=map:0, root UUID 442af407-....
- `/boot/mainline/`: dtb `sun60i-a733-orangepi-zero3w.dtb` (AC101 enabled) + MANY backups (see AGENTS.md)
- boot.scr loads mainline/{tiny-uInitrd, Image, dtb}; mainline dir currently lacks Image (tiny-uInitrd + dtbs only)
- dtb symlink → dtb-6.6.98-sun60iw2 (vendor tree dirs still present for recovery)

## DTB decision
- **KEEP the AC101-enabled dtb** (`ac101@1a` present in live device tree, model sun60iw2).
  AC101 audio working, no panic regression. No need to bisect the old backups.
- For ISO/kernel deliverable: always ship kernel complete with dtb (see KERNEL-ISO.md).

## Coredumps
- `/etc/sysctl.d/99-coredump.conf` → `kernel.core_pattern=/cores/core_%e_%p`
- `/cores` created 0777. NOTE: no cores captured yet (the greeter crash pre-dates activation).

## Reverting
- If ever needed: restore `/opt/vendor-gpu-bak/*` back to `/usr/local/lib/` and re-enable
  `/etc/ld.so.conf.d/00_xserver-xorg-img-bxm.conf` (currently `.disabled`), then `ldconfig`.