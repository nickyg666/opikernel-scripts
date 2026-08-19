# GPU-MESA.md — vendor GL purge, /opt/mesa-gpu, powervr stack

## The purge (why the display stack was broken)
Vendor GPU userspace lived in `/usr/local/lib` (from the `00_xserver-xorg-img-bxm.conf` ld.so path):
- libEGL.so.1, libgbm, libglapi, `dri/` dir, glmark2, gst plugins, etc.
- Because `/usr/local/lib` precedes `/lib/aarch64-linux-gnu`, system Mesa was shadowed.
- Symptoms: `libEGL fatal: did not find extension DRI_IMAGE_DRIVER version 1` in Xorg log,
  xvfb crash-looping, gnome-shell SIGSEGV (memory runaway 1.1G→4.3G, heap 1.5G).

### Applied fix (REVERSIBLE)
1. `/usr/local/lib/*.vendor-bak` and `/usr/local/lib/dri.vendor-bak` → moved to `/opt/vendor-gpu-bak/`
2. `/etc/ld.so.conf.d/00_xserver-xorg-img-bxm.conf` → renamed `.disabled`
3. `sudo ldconfig`
4. Verify: `ldconfig -p | grep -E "libEGL|libgbm"` must resolve to `/lib/aarch64-linux-gnu/`

Reversal: move `/opt/vendor-gpu-bak/*` back to `/usr/local/lib/`, re-enable the conf, ldconfig.

## System Mesa (now active)
- `/usr/lib/aarch64-linux-gnu/libEGL*`, `libgbm*`, `libGL*`, `libglapi*` — stock Ubuntu 26.04 (mesa 26.x)
- DRI drivers: `/usr/lib/aarch64-linux-gnu/dri/` (swrast/kmsro/...)
- Works in practice: Xorg runs, Xfce runs on Xorg, mutter init runs, powervr renderer node used.

## /opt/mesa-gpu (custom mesa 26.0.8 build with powervr Vulkan)
- Build dir on board: `/opt/mesa-gpu` (owner orangepi)
- `lib/libgallium-26.0.8.so` + symlinks `kmsro_dri.so`, `softpipe_dri.so`, `swrast_dri.so`, `zink_dri.so`
- `lib/libvulkan_powervr_mesa.so` (+ `.bak-0207` older copy) — the ALLWINNER PowerVR Vulkan driver
- `share/vulkan/icd.d/powervr_mesa_icd.aarch64.json`
- `lib/gbm/dri_gbm.so` (+ `.bak`)
- PowerVR kernel driver: mainline `powervr` DRM driver (card3, renderD128) — per MAINLINE-KERNEL.md on board

## gdm drop-ins (current state)
- `/etc/systemd/system/gdm.service.d/mesa-env.conf` — SLIMMED to `Environment=EGL_PLATFORM=gbm`
  (earlier it pointed `LIBGL_DRIVERS_PATH=/opt/mesa-gpu/lib/dri`, `GBM_BACKENDS_PATH=/opt/mesa-gpu/lib/gbm`,
  `VK_ICD_FILENAMES=...powervr_mesa_icd.aarch64.json`, `PVR_I_WANT_A_BROKEN_VULKAN_DRIVER=1`,
  `MESA_LOADER_DRIVER_OVERRIDE=zink` — REVERTIBLE breadcrumbs if the mesa-gpu path is wanted again)
- `/etc/systemd/system/gdm.service.d/seat-fix.conf` — seat fixes

## mutter/powervr live evidence (manual greeter run)
```
libmutter-Message: Added device '/dev/dri/renderD128' (powervr) using no mode setting.
libmutter-Message: Failed to initialize accelerated iGPU/dGPU framebuffer sharing: Not hardware accelerated
libmutter-Message: Created gbm renderer for '/dev/dri/renderD128'
```
→ The powervr device IS picked up; "Not hardware accelerated" is informational given dGPU-less system.

## Vulkan ICD files
- Board: `/opt/mesa-gpu/share/vulkan/icd.d/powervr_mesa_icd.aarch64.json` (exists, 183 bytes)
- Crash file `/var/crash/_opt_mesa-gpu_lib_libEGL.so.1.0.0.1000.crash` (Aug 16) is historical — pre-purge.

## When to touch this
- Only if GNOME needs zink/powervr Vulkan (e.g. mutter wants Vulkan for Wayland). Current strategy:
  GNOME on Xorg with system Mesa — needs NO mesa-gpu env. Keep mesa-env.conf slim.
- If Wayland sessions are ever desired: re-add the zink/powervr env vars and validate with a manual
  greeter run BEFORE restarting gdm.