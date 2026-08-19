# Mainline kernel bring-up (parallel to the vendor 6.6.98 stack)

This board is also brought up on a **mainline 6.18.19+ hybrid kernel** (see
`/boot/mainline/` on the SD). It is the *other* boot path: the vendor `uImage`
fallback vs. the mainline `Image` (gated by `/boot/mainline/armed`). Everything
below is about the MAINLINE path, which is independent of the vendor `sun60iw2`
stack described in AGENTS.md.

## Status (2026-08-14)

- **Boot**: mainline `6.18.19+ #9 SMP PREEMPT` boots to **Ubuntu 26.04 LTS**
  userspace (systemd 259.5), login `orangepi@orangepizero3w`. Root = `/dev/mmcblk1p1`
  (LABEL `opi_root`), single ext4 partition.
- **WiFi (AIC8800 SDIO)**: WORKS. `wlan0` (`a8:13:32:9c:8c:c0`) via
  `aic8800_fdrv` + `aic8800_bsp` (vendor SDIO driver ported 6.6.98→6.18).
  NetworkManager connects to `Lasagna` (5GHz WPA2) → DHCP `192.168.0.151`.
- **GPU (mainline powervr driver)**: NOW WORKS at the kernel level.
  `powervr 1800000.gpu` initializes (`[drm] Initialized powervr 1.0.0 for
  1800000.gpu on minor 1`), `/dev/dri/renderD128` = 1800000.gpu, IRQ live.
  BVNC = **36.56.104.183 (BXM-4-64)**.

## How the mainline GPU was made to work

1. **DTB**: deployed DTB `sun60i-a733-orangepi-zero3w.dtb` GPU node changed:
   `compatible = "img,img-rogue"` (was `img,gpu`), and `core`/`sys` clock
   names added (`clocks`/`clock-names` appended `0x12 0x88`=core, `0x12 0x89`=sys).
2. **Kernel patch** (`drivers/gpu/drm/imagination/pvr_power.c`): made
   `pvr_power_domains_init()` return 0 when the GPU node has **no**
   `power-domains` property (vendor powers the GPU via the NSI PMU, not Linux
   genpd; without this the driver silently failed probe with -ENOENT).
   Rebuilt `powervr.ko` (`make M=drivers/gpu/drm/imagination`).
3. **Firmware**: use the FREEDESKTOP MAINLINE firmware, NOT the vendor blob:
   `rogue_36.56.104.183_v1.fw` (131072 B) from
   `gitlab.freedesktop.org/imagination/linux-firmware` branch `powervr`,
   path `powervr/rogue_36.56.104.183_v1.fw`, installed at
   `/lib/firmware/powervr/rogue_36.56.104.183_v1.fw`.
   The vendor `rgx.fw.36.56.104.183` renamed to that name loads but is
   rejected: `Unsupported fw info version 2` (mainline needs fw-info v3).
4. **Userspace caveat**: the installed `libVK_IMG.so` (24.2.6603887, in
   /usr/lib) is the VENDOR user-mode driver for the vendor img-bxm kernel —
   it does NOT talk to the mainline powervr DRM. To use the mainline GPU you
   need **Mesa's Imagination Vulkan driver** (`-Dvulkan-drivers=...,imagination`),
   which Ubuntu does not ship by default. With the vendor ICD a plain
   `vulkaninfo` shows only llvmpipe. Not done yet.

## Kernel source / build (host machine `/home/tab`)

- Tree: `/home/tab/kernel-build/mainline-6.18` (linux-stable 6.18.19 + vendor
  BSP drivers grafted under `bsp/`). Build on host only, `-j2`, export
  `BSP_TOP=$(pwd)/bsp ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-`.
- Boot artifacts live in `/boot/mainline/` (Image, tiny-uInitrd, DTB, `armed`).
- Boot script `/boot/boot.cmd`→`boot.scr`; vendor `booti` relocates the initrd
  so keep it < 16 MiB (BL31 overlap = silent death).
- Project repo (host): `/home/tab/projects/orangepi-zero3w-mainline` (no remote
  yet). This board's display/GPU work repo: `ili9486impl`.

## Serial / network access

- OP serial relay = Banana Pi at `192.168.0.173` (root, pw `1`); OP UART0
  `console=ttyS0,115200` (`earlycon=uart,mmio32,0x2500000`).
- OP ssh: `orangepi@192.168.0.151` (pw `1`, passwordless sudo).
- Sudo from scripts: `SUDO_ASKPASS=/home/orangepi/.opencode-askpass sudo -A`.
- Do NOT run `opencode-web.service` at boot (it enabled a 0.0.0.0:1234 web
  agent endpoint and coincided with a reproducible kernel heap panic during
  early systemd; disabled via `multi-user.target.wants`).

## Git push

- Repos here use https remotes embedding a GitHub PAT (see `git config
  remote.origin.url`). Treat it as a secret; do not copy it into tracked files.
- `ili9486impl` → `github.com/nickyg666/orangepi-zero3w-ili9486-display`.
- Commit context changes here with `git -C /home/orangepi/ili9486impl commit`.
