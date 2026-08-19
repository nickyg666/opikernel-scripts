# opikernel — Orange Pi Zero 3W project archive (host-side)

One-stop snapshot of all project knowledge, scripts, and board configs.

## Layout
- `AGENTS.md` — MASTER FILE. Start here for cold-start context (inventory, state, next steps, constraints)
- `docs/` — deep-dive knowledge:
  - `BOARD-RECOVERY.md` — panic mystery resolution, serial capture, dts/dtb decisions
  - `DISPLAY-STACK.md` — GNOME/gdm/Xorg/Xfce saga, spi-mirror, DRM/fb layout, session switching
  - `GPU-MESA.md` — vendor GL purge, /opt/mesa-gpu, powervr, gdm drop-ins
  - `KERNEL-ISO.md` — kernel 6.18 build, dtb, Ubuntu 26.04 ISO deliverable, apt warnings
  - `WATCHER-SERIAL.md` — watcher box + serial console rules (ttyS0 root-600 gotcha)
  - `WYZE-SMARTPLUG.md` — power control, device id, recovery playbook, TLS/CA notes
  - `board-sync/` — pulled from board `/home/orangepi/ili9486impl/docs/` (GPU, MAINLINE-KERNEL, WAYLAND)
    + legacy host docs `ili9486_README.md`, `ili9486_AGENTS+source.txt`
- `scripts/host/` — host-side scripts (smartplug.py + wyze SDK files, boot_retry.sh, opi_boot_fix.sh, askpass.sh, off.py)
- `scripts/board/` — board-side binaries/sources (spi-mirror + fixed C + select script + old 32bpp binary)
- `scripts/watcher/` — watcher boot capture scripts (uboot_catch.sh, uboot_boot_*.sh)
- `config/` — exact board config exports:
  - systemd units: `spi-mirror.service`, `xvfb-virtual-display.service`
  - gdm drop-ins: `mesa-env.conf`, `seat-fix.conf`; `custom.conf`
  - Xorg: `10-lcd-modesetting.conf`
  - `orangepiEnv.txt`, `99-coredump.conf`, `00_xserver-xorg-img-bxm.conf.disabled`
  - `AccountsService-orangepi` (Session=ubuntu-xorg)
  - dtb + initrd: `sun60i-a733-orangepi-zero3w.dtb` (shipped/active), `tiny-uInitrd`

## Kept in place (originals, do not delete)
- `/home/tab/kernel-build/` — kernel 6.18 source (mainline-6.18, boot-mainline/{Image,uImage}),
  allwinner-bsp, build logs (build-error.log, modules-build*.log, modules-install.log, uart-build.log)
- `/home/tab/github_PAT` — GitHub PAT (never print; remote URL embeds it)
- `/home/tab/.venv-wyze` — Python env for smartplug/wyze scripts
- Board `/home/orangepi/ili9486impl/` — ili9486 project repo (has its own AGENTS.md, README, docs/)
- Board `/home/orangepi/uart_capture/` — live serial logs and legacy boot scripts
- Board `/opt/mesa-gpu`, `/opt/vendor-gpu-bak`, `/opt/kernel-build` — GPU/mesa + kernel trees
- Watcher `/home/orangepi/uart_capture/` — live serial capture

## Restore recipes
- Restore a board config file: `scp config/<name> <board-root>` (owner/permissions matter:
  AccountsService file must be root:root 600; systemd units root:root 644 then `daemon-reload`)
- Re-deploy spi-mirror: `scp scripts/board/spi-mirror <board>:/home/orangepi/spi-mirror` + restart service
- Power-cycle board: `python3 scripts/host/smartplug.py D03F271583AE off|on` (run in `.venv-wyze`)

## Status
Snapshot committed. Board was UP & stable (kernel 6.18.19+, AC101 dtb), Xfce-on-Xorg working,
GNOME greeter still failing (see AGENTS.md + docs/DISPLAY-STACK.md), HDMI unconfirmed,
kernel+dtb+ISO deliverable pending.