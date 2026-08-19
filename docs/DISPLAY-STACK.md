# DISPLAY-STACK.md — full saga of video/session state (GNOME, Xorg, Xfce, SPI mirror)

## Timeline of what happened
1. User reported "no video on HDMI again, frozen at boot screen" and frozen black cursor on SPI display.
   Kernel was healthy the whole time — the hang was the display stack (mutter/GNOME), not the kernel.
2. Diagnosis: gdm up but NO session; xvfb-virtual-display crash-looping (13,167 restarts,
   `MESA_LOADER` failing to find DRI in `/usr/local/lib/dri`); gnome-shell SIGSEGV ×5
   (memory 1.1G→4.3G peak, heap 1.5G).
3. ROOT CAUSE: vendor GPU userspace in `/usr/local/lib` (libEGL, libgbm, libglapi, dri/) shadowed system Mesa.
   Xorg log ended at `libEGL fatal: did not find extension DRI_IMAGE_DRIVER version 1`.
   Xorg conf pointed `kmsdev /dev/dri/card0` = the SPI panel (mainline card0=ili9486, HDMI is card1).
4. FIX (applied): moved `/usr/local/lib/*.vendor-bak` + `dri.vendor-bak` → `/opt/vendor-gpu-bak/`,
   disabled `/etc/ld.so.conf.d/00_xserver-xorg-img-bxm.conf` (→ `.disabled`), `ldconfig`.
   System Mesa now resolves libEGL/libgbm. Xfce came up on Xorg: `Xorg vt7` + `xfce4-session`
   running, HDMI mode 720x480, user confirmed desktop works.

## Current crisis (Aug 19)
- Xorg :manual works, Xfce works on Xorg. GNOME greeter under gdm DOES NOT start:
  - journal: `Gdm: GdmDisplay: Session never registered, failing` (×8)
  - `GdmLocalDisplayFactory: maximum number of display failures reached. Giving up.`
  - greeter child processes "already dead" ~3s after spawn.
- Manual greeter run WORKS (as root, on `Xorg :4`):
  `DISPLAY=:4 XAUTHORITY=/tmp/xgr/auth EGL_PLATFORM=gbm XDG_RUNTIME_DIR=/run/user/125 gnome-shell --mode=gdm`
  → libmutter: `Added device '/dev/dri/renderD128' (powervr)`, `Failed to initialize accelerated
  iGPU/dGPU framebuffer sharing: Not hardware accelerated`, `Created gbm renderer for '/dev/dri/renderD128'`.
  Then dies only due to missing session bus (that's MY sandbox, not gdm's).
- As `gdm-greeter` user: `su: user gdm-greeter does not exist or the user entry does not contain all
  the required fields` — suspect `/etc/passwd`/UID bookkeeping in the vendor image, gdm creates
  per-display users `gdm-greeter`, `gdm-greeter-2`. CHECK `getent passwd gdm-greeter`, `/etc/passwd`,
  `/etc/libnss-*` / NSS config. This is the top suspect for instant greeter death.
- No coredumps yet (`/cores` empty). Old crash files (NOT current state):
  - `/var/crash/_usr_bin_gnome-shell.1000.crash` (Aug 17 13:32, pre-purge, no backtrace stored)
  - `/var/crash/_opt_mesa-gpu_lib_libEGL.so.1.0.0.1000.crash` (Aug 16 00:48)
  - `/var/crash/_usr_bin_Xwayland.1000.crash` (Aug 16 02:07)

## Key configs (board)
- `/etc/gdm3/custom.conf`: `WaylandEnable=false`, `AutomaticLoginEnable=true`, `AutomaticLogin=orangepi`
- `/etc/xorg.conf.d/10-lcd-modesetting.conf`: `Option "kmsdev" "/dev/dri/card1"`, 720x480 mode
  (card0 = SPI, card1 = HDMI — MUST be card1)
- `/etc/systemd/system/gdm.service.d/mesa-env.conf` (only line now): `Environment=EGL_PLATFORM=gbm`
- `/etc/systemd/system/gdm.service.d/seat-fix.conf`: exists (seat fixes)
- `/var/lib/AccountsService/users/orangepi`: `[User] Session=ubuntu-xorg XSession=ubuntu-xorg`
- dconf `/org/gnome/desktop/session/session-name` = `'ubuntu-xorg'`
- AccountsService path is `AccountsService` (NOT `AccountService` — dead end trap)
- Restart accounts-daemon after editing AccountsService user files.
- GDM initializes display config at `/var/lib/gdm3/.config/monitors.xml` (Aug 2, context).

## DRM / fb layout (mainline 6.18.19+)
- `card0` ili9486 SPI panel (fb0, `ili9486drmfb`, 480x320, 16bpp RGB565 `format=0x00000005`)
- `card1` sunxi-drm: HDMI-A-1, DP-1, Writeback
- `card2` vkms/faux, `card3` powervr GPU; `renderD128` = powervr render node
- fb1/fb2 = `vkmsdrmfb`; `/dev/fb-lcd` symlink → fb0
- Modules: fb_ili9486, fbtft, ads7846 (touch), drm_mipi_dbi.ko present
- HDMI status right now: DISCONNECTED. dmesg: `hdmi drv detect hpd disconnect` + `select dvi output`
  at [111419]. NOT visually confirmed — user must eyeball monitor.

## Session switching knowledge
- `dconf write /org/gnome/desktop/session/session-name ubuntu-xorg` (user db)
- AccountsService file per user (required fields: [User], Session, XSession, SystemAccount)
- gdm caches sessions: after editing, restart `accounts-daemon` THEN `gdm`
- GNOME greeter failing leaves gdm in "gave up" state that survives until gdm restart; a restart DOES
  reset it (we saw it retry after restarts).

## Xvfb helper service
- `/etc/systemd/system/xvfb-virtual-display.service`: `Xvfb :1 -screen 0 1280x720x24`, Restart=always.
  Was part of the crash-loop problem (missing swrast in /usr/local/lib/dri); with system Mesa it should
  be fine. Disabled then re-enabled at various points — check `systemctl status` before relying on it.

## Next moves (ordered)
1. Check NSS/passwd for gdm-greeter (instant-death cause).
2. Restart accounts-daemon + gdm after any passwd fix; capture core if still crashing
   (`ls /cores`).
3. Get GNOME on Xorg (ubuntu-xorg), verify with user, then visually check HDMI.
4. Re-commit spi-mirror fix to `/home/orangepi/ili9486impl` (failed earlier: untracked test-utils/spi-mirror.c).

## spi-mirror details (they live on the BOARD)
- Source `/home/orangepi/spi-mirror.c`, binary `/home/orangepi/spi-mirror`
  (old 32bpp binary preserved as `spi-mirror.old-32bpp`)
- Sync target on board repo: `/home/orangepi/ili9486impl/test-utils/spi-mirror.c` (COMMIT PENDING)
- Service `/etc/systemd/system/spi-mirror.service`; selector `/usr/local/bin/spi-mirror-select.sh`
- FIX (confirmed by user "Spi mirrors correct now, gre8t job!"):
  - pack_pixel() writes per `fb_var_screeninfo` bitfields → correct RGB565 output (was 32bpp XRGB8888 → segfault + wrong colors)
  - per-frame `XGetWindowAttributes` → live resize/scale detection
  - build: `gcc -O2 -o spi-mirror spi-mirror.c -lX11`
- Selector logic: auth `/run/user/1000/gdm/Xauthority`, probes `:0 :2 :3`, external display check via
  `/sys/class/drm/card0-*/status`