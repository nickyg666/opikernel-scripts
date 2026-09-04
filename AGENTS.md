# AGENTS.md — Orange Pi Zero 3W (opikernel) session master

Everything needed to resume the project from a cold start. More detail in `docs/`.

## Goal
1. GNOME stable on the board (greeter/session working via Xorg; SPI mirror correct; HDMI confirmed)
2. Ship kernel 6.18 build (complete with dtb) + Ubuntu 26.04-capable ISO
3. Investigate `apt update` warnings

## Live inventory (Aug 19 2026)
- **Board**: Orange Pi Zero 3W `orangepizero3w`, IP `192.168.0.151`, user/pass `orangepi/orangepi`
  - SSH: `sshpass -p orangepi ssh -o StrictHostKeyChecking=accept-new -o PubkeyAuthentication=no -o Tunnel=no -o ConnectTimeout=8 orangepi@192.168.0.151`
  - Root: `echo orangepi | sudo -S <cmd>`
  - Kernel `6.18.19+ #12`, AC101 dtb active, stable (no 22s panic; up for hours)
- **Serial console (PRIMARY, since Aug 27)**: pico USB-serial bridge on the HOST
  (.168) — picoprobe `2e8a:000a` exposing `/dev/ttyACM0` wired to the board's UART
  pins @115200. Nick built this to replace the watcher UART; no second UART
  connection is needed. Capture: `sudo stty -F /dev/ttyACM0 115200 raw -echo` then
  `sudo setsid bash -c 'exec cat /dev/ttyACM0 >> /home/host/pvrgl-work/sercap2.log'`
  (persistent dir, NOT /tmp — /tmp wipes lose boot evidence). Writes to the port
  need root/sudo (crw-rw---- root:dialout). Commands are paced ~0.2s apart one
  line per write; output appears in the capture file. Enter-spam loop
  (~44×0.25s starting 2-3s after power-on) catches the U-Boot autoboot window.
- **Watcher (SECONDARY, offline since Aug 27)**: `192.168.0.167`, user/pass
  `orangepi/orangepi`, sudo same
  - Serial capture log grows: `/home/orangepi/uart_capture/ttyS0.log` (must run as root, see docs/WATCHER-SERIAL.md)
- **Host (this machine)**: `/home/tab`
  - Kernel source: `/home/tab/kernel-build/mainline-6.18`
  - GitHub PAT: `/home/tab/github_PAT` (NEVER print it)
  - Wyze venv: `/home/tab/.venv-wyze`, smartplug script `/home/tab/smartplug.py`

## Current state of the display stack (critical!)
- Xorg works manually + Xfce works on Xorg. GNOME greeter does NOT start under gdm
  (gdm: `Session never registered, failing` ×N then `maximum number of display failures reached. Giving up.`)
- Manual greeter run WORKS (`Xorg :4` + `gnome-shell --mode=gdm`): mutter init powerVR renderer OK
- Under gdm it dies silently in ~3s. gdm-greeter user looks broken:
  `su: user gdm-greeter does not exist or the user entry does not contain all the required fields`
  (passwd entry issue — check `getent passwd gdm-greeter` / `/etc/passwd`)
- No coredumps captured (`/cores` empty) — kernel.core_pattern set but nothing crashed while pattern active
- Old gnome-shell crash file `/var/crash/_usr_bin_gnome-shell.1000.crash` (Aug 17 13:32, pre-purge — NOT current)
- mesa EGL crash `/var/crash/_opt_mesa-gpu_lib_libEGL.so.1.0.0.1000.crash` (Aug 16 00:48)

### Key configs on board
- `/etc/gdm3/custom.conf`: WaylandEnable=false, autologin orangepi
- `/etc/xorg.conf.d/10-lcd-modesetting.conf` (X11): `kmsdev /dev/dri/card1` (HDMI), 720x480 mode
- `/etc/systemd/system/gdm.service.d/mesa-env.conf`: only `EGL_PLATFORM=gbm` remains
- `/etc/systemd/system/gdm.service.d/seat-fix.conf`: exists
- `/var/lib/AccountsService/users/orangepi`: `Session=ubuntu-xorg`, `XSession=ubuntu-xorg`
- dconf session-name: `ubuntu-xorg`
- `/opt/mesa-gpu`: mesa 26.0.8 build (libgallium, libvulkan_powervr_mesa.so, zink/softpipe/kmsro/swrast DRI symlinks, powervr ICD json)
- `/opt/vendor-gpu-bak`: purged vendor GPU libs (was `/usr/local/lib/*.vendor-bak`) — reversal possible
- `/etc/ld.so.conf.d/00_xserver-xorg-img-bxm.conf.disabled`: purged vendor ld entry
- `/cores`: core dump dir (777), sysctl `kernel.core_pattern=/cores/core_%e_%p`

### DRM layout (mainline)
- card0 = ili9486 (SPI panel), card1 = sunxi-drm (HDMI-A-1 + DP-1 + Writeback), card2 = vkms/faux, card3 = powervr GPU
- renderD128 = powervr
- fb0 = ili9486drmfb 480x320 RGB565 (16bpp), `/dev/fb-lcd` → fb0; fb1/fb2 = vkmsdrmfb
- HDMI status currently: `disconnected` (`/sys/class/drm/card1-HDMI-A-1/status`) — NOT visually confirmed by user

## Boot config
- `/boot/orangepiEnv.txt`: `verbosity=7 extraargs=fbcon=map:0 rootdev=UUID=442af407-cb84-48f8-845e-4be5cd18ce13`
- `/boot/mainline/`: dtb `sun60i-a733-orangepi-zero3w.dtb` (AC101-enabled, Aug 16 17:45) + backups:
  `bak-ac101-disabled`, `bak-826-sound-fix`, `bak-audio-usb-npu`, `bak-iommu-on`, `bak-iommuoff`,
  `bak-pckfix*`, `bak-rebuild-207742`, `bak-wifi`, `bak2`, `orig-*`
- `boot.scr` loads `${prefix}mainline/{tiny-uInitrd,Image,sun60i-a733-orangepi-zero3w.dtb}`;
  mainline dir currently has no Image (only tiny-uInitrd + dtbs)
- dtb symlink → `dtb-6.6.98-sun60iw2`
- ili9486 invariants (see board AGENTS.md): overlays=ili9486, fbcon=map:1, `/etc/modules-load.d/ili9486.conf`,
  watchdog rollback marker `/var/lib/ili9486-boot-count.rolled-back`

## Services on board
- `spi-mirror.service`: `/etc/systemd/system/spi-mirror.service`, selector `/usr/local/bin/spi-mirror-select.sh`
  (auth `/run/user/1000/gdm/Xauthority`, probes `:0 :2 :3`, ext check via `/sys/class/drm/card0-*/status`)
- `xvfb-virtual-display.service`: `Xvfb :1 -screen 0 1280x720x24`, Restart=always (had 13k+ crash loop when vendor GL shadowed system Mesa)
- `gdm.service` with drop-ins above
- Modules loaded: fb_ili9486, fbtft, ads7846, drm_mipi_dbi (.ko)

## Next steps (ordered)
1. Fix gdm-greeter passwd entry / verify greeter under gdm (check `getent passwd gdm-greeter`)
2. Get GNOME session up on Xorg (ubuntu-xorg). Verify gnome-shell doesn't crash w/o vendor GL
3. User visually confirms HDMI output; if disconnected, retrigger connector detect
4. Re-commit `test-utils/spi-mirror.c` in `/home/orangepi/ili9486impl` (last commit attempt failed: "nothing added to commit but untracked files present")
5. Investigate apt warnings; build kernel 6.18 + dtb + Ubuntu 26.04 ISO
6. Verify `git push github HEAD:main` completed (was still running; run `git ls-remote github HEAD`)

## Constraints / preferences
- User: "keep it movin", "K now fix gnome and everything else"
- Target GNOME via Xorg (ubuntu-xorg), NOT Wayland (mutter/Wayland was the crash loop)
- Keep vendor GL purge reversible (files staged in /opt/vendor-gpu-bak)
- Do NOT print GitHub PAT (`/home/tab/github_PAT`); remote URL embeds it
- Migration fallback if resources exhausted: host `192.168.0.168:/home/host/opikernel` (mkdir first; sudo pw there = `1`) — NOT needed so far
- Users asking questions about products → point to latest commit in repo
- MI3S phone is ok/listed