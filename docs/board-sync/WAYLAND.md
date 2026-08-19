# Wayland status

## RESOLVED (2026-08-05): Wayland works on the virtual display

The old blocker was mutter segfaulting on the SPI-panel X session when the
sunxi-drm HDMI connector emitted a disconnect event (g_str_has_prefix NULL
assert). The whole display architecture has since moved to "virtual display +
mirror", so the panel no longer runs a compositor directly - the virtual
display does, and spi-mirror copies it to the panel.

## Current setup (all systemd services, auto-start at boot)

- xvfb-virtual-display.service : Xvfb :1 at 1920x1080x24 (the "dummy display",
  always present regardless of physical hardware)
- weston-virtual.service       : Weston 9 Wayland compositor ON :1 (x11 backend,
  gl renderer), socket /run/user/1000/wayland-0
- spi-mirror.service           : grabs :1 root window, box-filters 1920x1080 ->
  480x320 RGB565, writes to /dev/fb-lcd; kernel shadow-diff pushes changed
  blocks over SPI

## Using Wayland apps

    export XDG_RUNTIME_DIR=/run/user/1000
    export WAYLAND_DISPLAY=wayland-0
    weston-terminal     # or any Wayland-native app

Everything shows up on the SPI panel via spi-mirror.

## Notes

- Weston on :1 uses softpipe (CPU) for its GL renderer unless zink is made
  findable in /usr/local/lib/dri. GPU apps (Minecraft via zink GLX on :1) still
  render on the PowerVR; the compositor blit is the only CPU part.
- The old mutter-on-SPI approach is abandoned; do not reintroduce it.
