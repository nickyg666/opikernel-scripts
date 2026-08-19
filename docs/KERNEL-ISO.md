# KERNEL-ISO.md — kernel 6.18 build, dtb, Ubuntu 26.04-capable ISO deliverable

## Deliverable (user request)
"ensure we ship a kernel build complete with dtb and ubuntu 26.04 capable iso"
Also: `apt update` produces a slew of warnings — investigate as part of this.

## Where everything lives (HOST = /home/tab)
- Mainline kernel source: `/home/tab/kernel-build/mainline-6.18` (branch `allwinner-linux-6.18`)
  - remote `github` → nickyg666/OrangePiZero3W-kernel6.18
  - PAT file: `/home/tab/github_PAT` (NEVER print; remote URL embeds it)
  - Kernel built: `6.18.19+ #12` — installed ON the board (running)
- Build logs (host): `/home/tab/kernel-build/{build-error.log, modules-build*.log, modules-install.log, uart-build.log}`
- Also on host: `/home/tab/kernel-build/allwinner-bsp` (vendor BSP tree)
- Board-side: `/opt/kernel-build` exists (kernel sources on board)

## Board boot chain (what "complete with dtb" means)
- `/boot/mainline/boot.scr` loads `${prefix}mainline/{tiny-uInitrd, Image, sun60i-a733-orangepi-zero3w.dtb}`
- CAUTION: mainline dir currently has NO Image (only tiny-uInitrd + dtb backups) — the running kernel
  is booted via the vendor boot.scr path. Do not prune blindly.
- `/boot/mainline/sun60i-a733-orangepi-zero3w.dtb` = AC101-enabled (Aug 16 17:45) — SHIP THIS ONE
- DTB backups retained (see AGENTS.md list) for A/B testing
- `/boot/orangepiEnv.txt`: verbosity=7, `extraargs=fbcon=map:0`, rootdev UUID 442af407-...
- dtb symlink → `dtb-6.6.98-sun60iw2`

## APT warnings (pending investigation)
- User: "apt update causes a slew of warnings" — likely:
  - stale `/etc/apt/sources.list.d/*.list` from vendor image (deb822 vs legacy format)
  - missing Ubuntu 26.04 pockets for this arch/mirror
  - third-party repos (e.g. xserver-xorg-image, anydesk, wyze) with weak/deprecated keys
- Action: run `apt update` capture warnings; audit `/etc/apt/sources.list*`, `/etc/apt/sources.list.d/`;
  fix/quiet them; then build ISO.

## ISO plan (next steps, not started)
1. Audit apt sources + fix warnings
2. Reproduce a clean kernel build incl. dtb install rules:
   - `make ... Image`, dtbs, modules_install, then cp dtb + Image + tiny-uInitrd into an ISO payload dir
   - Validate `boot.scr`-compatible layout
3. Build Ubuntu 26.04-capable ISO (check existing tooling on host: check `ls /home/tab` for ISO tools —
   none seen yet; likely `xorriso`/`genisoimage` or ubuntu-cdimage if we install it)
4. Mount-test ISO on the board (or verify layout offline)

## Kernel build recipe (from prior session history)
- Source: `mainline-6.18` dir; defconfig family `allwinner`/custom config with:
  - AC101 codec, ili9486 DRM panel (drm_mipi_dbi), fb_ili9486, fbtft, ads7846
  - powervr DRM GPU driver (renderD128)
  - vkms/faux card (-VRAM vkms)
- Built uImage + dtb + modules; modules installed to board `/usr/lib/modules/6.18.19+`
- Kernel cmdline additions: `fbcon=map:0`

## Post-ISO checklist
- Boot board from ISO (or verify layout) → expect: kernel 6.18.19+, AC101 dtb, no panic, UI up
- Confirm `apt update` clean
- Push kernel repo: `git push github HEAD:main` (was still running — verify with `git ls-remote github HEAD`)