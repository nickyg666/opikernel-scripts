# GPU Status (PowerVR)

## Hardware
- GPU: PowerVR B-Series BXM-4-64 MC1 (Rogue)
- Kernel driver: pvrsrvkm.ko (DKMS, v24.2.6603887) - creates /dev/dri/card2
- DRM pvr driver initialized on minor 2

## Userspace drivers (present)
- Vulkan: libVK_IMG.so (v24.2.6603887) at /usr/lib/, ICD /usr/share/vulkan/icd.d/img_icd.json
  - VERIFIED WORKING: vulkaninfo reports PowerVR BXM-4-64 MC1, API 1.3.277
- OpenGL/EGL: pvr_dri.so + vendor mesa WSI (libpvr_mesa_wsi.so) in /usr/local/lib/
- Mesa pvr_dri.so at /usr/lib/aarch64-linux-gnu/dri/pvr_dri.so (not auto-selected)

## Current GL situation
- X session uses fbdev (fb1) -> GLX falls back to llvmpipe (software)
- GPU is NOT used for desktop compositing yet

## To use the GPU
1. Configure Mutter/gnome-shell to use PowerVR EGL (vendor libs in /usr/local/lib)
2. Or use Vulkan directly for compositing/downscale
3. GPU could accelerate: gnome-shell compositing, box-filter downscale (960x640->480x320)

## GL/EGL integration findings
- Vendor GL stack (/usr/local/lib, Mesa 24.0.1) initializes but only via zink (Vulkan-over-GL)
- zink_dri.so missing from /usr/local/lib/dri -> falls back to softpipe (software)
- System Mesa (23.2.1) + system zink_dri.so exist but version-mismatch with vendor EGL
- zink over X11 GLX fails DRI2 auth -> GL_RENDERER null
- CONCLUSION: GL desktop compositing via GPU not feasible without vendor fix.
  Raw Vulkan WORKS (PowerVR BXM-4-64, API 1.3.277) - usable for custom rendering
  (e.g. GPU-accelerated video player -> downscale -> SPI framebuffer).

## Updated findings (post-gpu-vpu install)
- Vendor /usr/local/lib/dri/pvr_dri.so HAS __driDriverGetExtensions_pvr
- But vendor EGL (Mesa 24.0.1) falls back to softpipe even with
  MESA_LOADER_DRIVER_OVERRIDE=pvr - pvr DRI driver fails to initialize
  (DRI2 auth under X11/fbdev)
- Vulkan works fully (libVK_IMG, PowerVR BXM-4-64 MC1, API 1.3.277)
- CONCLUSION: desktop GL compositing via PowerVR not working in this
  X11+fbdev config; vendor EGL is Mesa 24.0.1 but pvr_dri silently fails.
  Use Vulkan for custom GPU rendering. Temps OK at 61C idle (llvmpipe
  only burns CPU when actively compositing).

## BREAKTHROUGH: PowerVR GL WORKS with the right env
Command that yields GPU GL rendering:
  LD_LIBRARY_PATH=/usr/local/lib \
  LIBGL_DRIVERS_PATH=/usr/local/lib/dri \
  MESA_LOADER_DRIVER_OVERRIDE=pvr \
  EGL_PLATFORM=surfaceless \
  <gl app>
Result:
  GL_VENDOR: Imagination Technologies
  GL_RENDERER: PowerVR B-Series BXM-4-64
The vendor Mesa stack (/usr/local/lib, from Incipiens GPU-VPU) DOES work.
Earlier failures were because EGL_PLATFORM defaulted to x11 (broken) and
the pvr driver wasn't forced. surfaceless + override=pvr is the key.
Next: wire this env into gnome-shell/Mutter for GPU compositing, and
into the Wayland session (which previously crashed on EGL init).

## CAUTION: pvr GL works standalone but breaks mutter
- eglgl test: pvr works with EGL_PLATFORM=surfaceless (PowerVR BXM-4-64)
- BUT setting MESA_LOADER_DRIVER_OVERRIDE=pvr globally (Xsession.d) makes
  gnome-shell/mutter CRASH (g_str_has_prefix NULL -> signal 11) because
  mutter uses the x11 EGL platform, which the vendor stack can't handle.
- REVERTED: removed Xsession.d/99-pvr-gpu and /etc/environment overrides.
- The Wayland crash is the SAME x11-EGL/card0 issue. Standalone pvr GL
  (surfaceless) works; integrating into mutter needs the x11/EGL platform
  working (vendor stack gap) or mutter patched.
- Current state: X11 desktop stable, llvmpipe GL (CPU). GPU usable via
  standalone Vulkan/GL apps with surfaceless+override=pvr.

## PROVEN: GPU -> SPI framebuffer pipeline works
test-utils/gpu_fbo.c renders a GL gradient on the PowerVR GPU (EGL
surfaceless + pvr override), reads it back from an FBO, converts to RGB565,
and writes to /dev/fb0 (which the mipi_dbi driver flushes to SPI).
Output: "GPU GL: PowerVR B-Series BXM-4-64", readback gradient px[0]=160,142,71.
This is the path for GPU-accelerated apps (video players, games) that
bypass mutter's broken EGL: render offscreen on GPU -> write fb -> SPI.
Note: wrote a 480x320 frame into the 960x640 fb (top-left quadrant);
a real app should render at 960x640 and box-filter, or the driver should
scale. This proves the hardware path; app integration is the next step.

## Minecraft/GLX GPU paths (tested)
1. Native pvr GL (MESA_LOADER_DRIVER_OVERRIDE=pvr): works SURFACELESS
   (offscreen FBO readback -> fb proven). FAILS GLX window: DRI2 auth /
   X_GLXCreateNewContext BadValue on the fbdev X server.
2. zink (GL-over-Vulkan, MESA_LOADER_DRIVER_OVERRIDE=zink): reaches PowerVR
   (glxinfo shows "zink Vulkan 1.3 PowerVR BXM-4-64") but fails because the
   GPU lacks fillModeNonSolid (zink base requirement) -> swapchain error.
   Also "some incorrect rendering" warning.
=> No GLX window path to the GPU on this setup. GPU usable offscreen only
   (surfaceless + FBO readback -> write fb). Minecraft on llvmpipe; use
   480x320 window (instance.cfg OverrideWindow) for 4x faster rendering.

## GLAMOR/modesetting experiment (tested)
- modesetting driver on card1 (SPI, ili9486): sees "Unknown19-1" output, probed
  modes OK, but glamor initialization FAILS on card1 (mipi_dbi has no GPU).
- modesetting driver on card0/GPU: "glamor X acceleration enabled on PowerVR
  B-Series BXM-4-64" - GLAMOR DOES init on the PowerVR via modesetting!
- But screen binds to card1 (display), which can't glamor -> "no screens found".
- CONCLUSION: GPU (card2) and display (card1) are SEPARATE DRM devices. To use
  GPU glamor for the SPI display, the GPU would need to render INTO card1's
  framebuffer - complex cross-device setup not feasible here.
- zink needs DRI3 for presentation; fbdev X has no DRI3 -> GPU GL can't present
  to windows on this display. pvr GL works offscreen only (surfaceless).

## Chromium WebGL (ANGLE-on-Vulkan) - WORKS
- chromium with --use-gl=angle --use-angle=vulkan --enable-features=Vulkan
  - GPU process opens /dev/dri/renderD128 (pvr) - confirmed via /proc fds.
- This bypasses GLX/DRI3 entirely (Chromium uses its own Vulkan WSI), so it
  can present GPU-rendered WebGL to the X window even on fbdev.
- This is the most viable GPU-windowed path on this setup. Desktop shortcuts:
  ~/Desktop/chromium-webgl-test.desktop (aquarium), chromium-gpu-info.desktop.

## MODESETTING X ON CARD1 - WORKS (DRI3 enabled!)
Config: /etc/X11/xorg.conf.d/10-lcd-modesetting.conf (modesetting on card1,
AccelMethod none). Desktop now runs on modesetting driver with:
  - DRI3 + Present + GLX initialized
  - 960x640 on the SPI display
This replaces the fbdev config. Key: DRI3 now EXISTS (was missing on fbdev).
GL presentation still not working:
  - zink: reaches PowerVR but swapchain fails + fillModeNonSolid warning
  - pvr GLX: "failed to load driver swrast" / X_GLXCreateNewContext BadValue
Note: modesetting X may strobe when GL clients crash during present attempts.

## ROOT CAUSE of all Vulkan-swapchain failures: PowerVR WSI is 256x256 only
vulkaninfo on the PowerVR BXM-4-64 surface:
  minImageCount = 3
  currentExtent  = 256x256 (FIXED)
  minImageExtent = 256x256
  maxImageExtent = 256x256 (implied)
This is a HARD constraint of the PowerVR DRM WSI: no window can get a
swapchain other than 256x256. Therefore:
  - zink GL-over-Vulkan: swapchain must be 256x256, window is 960x640 -> fail
  - Chromium ANGLE-on-Vulkan: same constraint -> cannot present fullscreen
The GPU's only working path is OFFSCREEN (surfaceless) rendering -> FBO
readback -> write fb (gpu_fbo.c proves this works at any size).
=> The Vulkan window-presentation path is architecturally capped at 256x256
   on this GPU/driver combo. Not fixable in userspace.

## FINAL: native pvr GL GLX-window path is impossible
The vendor GL stack (/usr/local/lib, Mesa 24.0.1) has EGL/GLES only - NO
desktop libGL. So pvr_dri.so (24.0.1) can only be used via vendor EGL, not
system GLX (23.2.1). Attempting GLX gives "DRI driver not from this Mesa
build (24.0.1 vs 23.2.1)".
Combined with the 256x256 Vulkan-WSI cap, the GPU CANNOT present to any
desktop window (GLX or Vulkan). It can only render offscreen:
  surfaceless EGL (pvr) or Vulkan -> FBO readback -> write /dev/fb0.
That offscreen->fb path is PROVEN (gpu_fbo.c). Minecraft/windowed GPU GL
is not achievable on this platform/driver combo.

## CONFIRMED ROOT CAUSE of glamor "hang/crash" (2026-08-06)
Tested the exact glamor requirements against the BSP stack on card0 (HDMI):
- The BSP vendor stack is coherent Mesa 24.0.1 everywhere (/usr/local/lib, /usr/local/lib/dri).
- EGL+GBM on card0 works: standalone program (`glamtest`) creates an EGL window surface,
  makes current, swaps, and reports `PowerVR B-Series BXM-4-64`, GLES 3.2. So the real GPU
  CAN render on the display card via BSP EGL/GLES.
- BUT glamor needs a **desktop OpenGL** context: it calls `eglBindAPI(EGL_OPENGL_API)`.
  The BSP stack has EGL/GLES ONLY — no desktop GL. `eglBindAPI(EGL_OPENGL_API)` returns
  EGL_BAD_MATCH (0x300c); there is no `EGL_OPENGL_BIT` config, and there is NO libGL in
  /usr/local/lib (only libGLESv1_CM.so / libGLESv2.so).
- The system mesa 23.2.1 stamp HAS desktop GL + zink, but `kmsro: driver missing`
  (no sunxi-drm/pvr for the PowerVR) -> cannot bind the GPU. Attempting to pair
  system zink (23.2.1) with BSP EGL (24.0.1) gives "DRI driver not from this Mesa build".
- Consequence: when `AccelMethod "glamor"` is set on card0, modesetting GPU EGL init fails
  ("libEGL fatal: did not find extension DRI_IMAGE_DRIVER version 1"), X aborts
  ("Unable to run X server", autologin fails). The old note said "glamor hangs" — it does
  not hang, it aborts because the vendor EGL cannot supply desktop GL to glamor.
- This is a hard driver constraint: the only Mesa that drives the PowerVR (BSP 24.1.1)
  exposes GLES only, and glamor is hard-coded for desktop GL. NOT fixable in config.
- Working desktop/3D on this board: zink (GL->Vulkan on the real GPU) + `MESA_VK_WSI_DEBUG=sw`
  for software present, or offscreen (surfaceless) -> FBO -> fb. Native Vulkan window
  present needs DRI3/Present (libpvr_mesa_wsi has xcb-dri3/xcb-present), which glamor
  cannot provide (needs desktop GL). Consistent with everything in docs/GPU.md.

## DRI3 on modesetting X is initialized but NOT functional
- modesetting X on card1 logs "Initializing extension DRI3" but
  `xdpyinfo -ext DRI3` reports NOT supported. DRI3 needs a functioning
  PRIME render-GPU provider; the PowerVR (card2) is a separate device not
  wired as a provider to card1. So DRI3 is advertised but can't hand out
  buffers.
- Chromium ANGLE-on-Vulkan still fails: "dri3 extension not supported" +
  "Failed to create vulkan surface". Its gpu-process also doesn't inherit
  VK_ICD_FILENAMES (spawned with clean env).
- CONCLUSION: NO GPU window presentation is possible on this setup (no
  functional DRI3, 256x256 Vulkan-WSI cap, no vendor libGL for GLX).
  GPU works ONLY offscreen (surfaceless -> FBO -> write fb), proven.

## GPU -> SPI DISPLAY AS A CARD DEVICE - WORKS (gpu_drm_demo.c)
When X is stopped (DRM master free), gpu_drm_demo:
  1. Renders animated frames on PowerVR (surfaceless EGL, 960x640)
  2. Copies GPU output into a card1 dumb-buffer framebuffer
  3. Flips the CRTC -> mipi_dbi flushes to SPI
SPI stats jumped ~1.1 billion bytes during the run => frames reached the panel.
This proves the GPU can drive the SPI display directly as a card device.
Test: systemctl stop gdm3; run gpu_drm_demo; systemctl start gdm3 to restore.
The demo takes over the screen while running (X stopped). Startup X config is
untouched so the desktop always returns on reboot.

## GPU renders alongside desktop (no X kill needed) - VERIFIED
With modesetting X on card1, /dev/fb0 maps to the ACTIVE scanout. So:
  gpu_demo (PowerVR offscreen render) -> write /dev/fb0 -> mipi_dbi flush -> SPI.
Verified: SPI +24,580 bytes in 2s while X was running; desktop stayed up.
This is the integration path: GPU-accelerated apps render offscreen on the
PowerVR and present to the SPI display by writing the scanout fb, coexisting
with the X desktop. gpu_demo.c and gpu_drm_demo.c demonstrate both modes.

## CORRECTION: gpu_demo via /dev/fb0 does NOT display alongside X
The CRTC scans out Xorg's buffer (fb=38, dma 0xffa00000). /dev/fb0 maps to
the fbcon buffer (fb=36, dma 0xff700000), which is NOT scanned out, and /dev/fb0
reports size 0 under modesetting X. So writing GPU frames to /dev/fb0 does
nothing visible (the SPI bytes observed were X's own redraws). X's scanout
GEM has no exported name, so external processes can't write into it.
CORRECT paths:
  - gpu_drm_demo: takes DRM master (stop X), flips GPU frames -> WORKS (proven)
  - Alongside X: NOT possible via fb0. Would need X cooperation or a GPU
    compositor owning the display.

## FINAL BLOCKER for DRI3/PRIME GPU offload: PowerVR has NO dumb buffers
The modesetting driver requires dumb-buffer support for ANY use (screen or
offload provider). card2 (PowerVR) has DUMB_BUFFER=0 -> modesetting crashes
"KMS doesn't support dumb interface". So the GPU cannot be a modesetting
offload provider, and DRI3 can't share GPU buffers with card1.
card1 (SPI) now HAS PRIME (DRIVER_RENDER added) but needs the GPU to export
buffers via modesetting, which the PowerVR can't (no dumb buffers).
=> Full DRI3 windowed GPU rendering is NOT possible with this PowerVR driver.
   The GPU works ONLY via its own EGL/Vulkan (surfaceless) rendering to
   card1's framebuffer (gpu_drm_demo) - the proven standalone path.

## FOREST-LEVEL: why ANGLE/DRI3 can't work on the SPI display
Incipiens (HDMI display, sunxi-drm) got Chromium ANGLE-on-Vulkan working:
  - Xorg on the HDMI DRM node (sunxi-drm) with a working DRI3/Present path
    serviced by the display controller.
  - Chromium's ANGLE creates a Vulkan WSI surface on X (needs DRI3/Present).
Our SPI display (mipi_dbi, card1) has NO display controller / presentation
engine - every frame is a software full-frame SPI flush. modesetting X here:
  - Initializes DRI3/Present but they're NOT advertised to clients (no
    GPU-backed glamor/EGL to service them) - confirmed: xdpyinfo says
    "not supported" despite "Initializing extension DRI3" in the log.
  - So ANGLE's Vulkan surface creation fails ("Failed to create vulkan surface").
This is a hardware difference (SPI panel vs HDMI), not a config error.
The working GPU path on SPI: render offscreen (surfaceless EGL/Vulkan) ->
write the scanout fb (gpu_drm_demo) - no X DRI3 needed.

## UPDATE (2026-08-03): zink GLX presentation WORKS via software-present fallback

The old conclusion ("GL desktop compositing via GPU not feasible") is OUTDATED.

### The fix: MESA_VK_WSI_DEBUG=sw
- Problem: zink presents GLX windows via the Vulkan X11 WSI, which requires the
  DRI3 X extension. This SPI-panel X server initializes DRI3 internally but
  never exposes it to clients ("screen 0 is not DRI2 capable" - no glamor/GBM
  on the ili9486 SPI DRM device). Result: "could not create swapchain",
  GLX window apps die at window creation.
- Glamor attempt FAILS: modesetting + AccelMethod glamor hangs Xorg at
  glamoregl init (no hardware EGL/GBM scanout path on the SPI panel).
- FIX: `export MESA_VK_WSI_DEBUG=sw` (Mesa WSI debug flag WSI_DEBUG_SW in
  src/vulkan/wsi/wsi_common.c:82). This forces the software present path
  (`x11_present_to_x11_sw`, XShmPutImage-based) which needs NO DRI3.
- Verified: `glxinfo -B` with zink + MESA_VK_WSI_DEBUG=sw reports
  "Device: zink Vulkan 1.3(PowerVR B-Series BXM-4-64 MC1), Accelerated: yes"
  and GLX window swapbuffers works (glxswaptest.c).

### Minecraft (NeoForge 26.1.2) on the GPU - WORKING
- PrismLauncher instance 26.1.2, Java 25 (java-runtime-epsilon)
- Launch: /home/orangepi/minecraft/game-run.sh -l 26.1.2
  env: MESA_LOADER_DRIVER_OVERRIDE=zink MESA_GL_VERSION_OVERRIDE=4.5
       MESA_VK_WSI_DEBUG=sw ALSOFT_DRIVERS=null
- OpenAL: libopenal.so segfaults in alcGetString enumerating devices with no
  audio server (hs_err: SoundEngine -> DeviceList.query). Fix: ALSOFT_DRIVERS=null.
- NeoForge early splash window needs GLX -> disable in fml.toml:
  earlyWindowControl = false
- Window: options.txt overrideWidth 960 overrideHeight 640 (fills 960x640
  desktop, downscaled 2x to panel), guiScale 1 (smallest UI so oak
  keyboard / GNOME OSK fit), fullscreen false, maxFps 60, vsync off.
- PrismLauncher refuses root; launch via su - orangepi (launch-detached.sh).

### Scale=2 supersampling (whole desktop)
- DT overlay sun60i-a733-ili9486.dts: scale = <2> -> DRM exposes 960x640
  virtual mode; mipi_dbi_scaled_fb_dirty box-filters 2x down to the 480x320
  GRAM. Every UI element renders at double res and appears HALF physical size
  (GNOME OSK + Minecraft UI fit on the panel). Free antialiasing; the GPU
  does the heavy lifting. Full-frame SPI = 1.23MB but shadow-diff flush only
  sends changed 16x16 blocks.
- X config: /etc/X11/xorg.conf.d/10-lcd-modesetting.conf Modes "960x640",
  DisplaySize 812 541 (keeps 30dpi effective after 2x downscale).

## pvr_offscreen: PowerVR offscreen render + dmabuf export (2026-08-06)

`gpu/pvr_offscreen.{c,h}` is a library that renders GLES3 frames on the PowerVR
(surfaceless EGL on `/dev/dri/renderD129`) into a GBM buffer and exports it as a
dmabuf fd (via `gbm_bo_get_fd`). No X/DRM master needed. `gpu/bench.c` got
250fps @1920x1080 on BXM-4-64 MC1.

## pvr_weston: GPU frames into Weston via zwp_linux_dmabuf_v1 (WIP)

`gpu/pvr_weston.c` is a fullscreen Wayland client: renders GLES on the PowerVR
into the exported dmabuf each frame, imports it into Weston with
`zwp_linux_dmabuf_v1_create_params` + add + create, and attaches to a surface
for presentation on the Weston output (DP-1/HDMI). Requires weston-drm running
as root with a world-writable socket (`XDG_RUNTIME_DIR=/run/weston-rt
WAYLAND_DISPLAY=wl-drm`).

## GBM format/modifier probe results on renderD129 (2026-08-06)

`gpu/probe_fmt.c` / `gpu/probe_mod.c` query what the PowerVR GBM backend can
create via `gbm_bo_create` on the render node. Run as root (node is
root:render, `open()` as user fails -> NULL device -> segv):

- RENDERING-only 1920x1080 buffers:
  - OK: XRGB8888, XBGR8888, ARGB8888, ABGR8888, RGB24 (stride 7680 / 5760 = 4/3 bpp linear)
  - FAIL: BGRX8888, BGRA8888, RGBX8888, RGBA8888, RG24("IMG2")
- Modifier on all successful buffers: `0xffffffffffffff` == GBM_MODIFIER_INVALID
  (implicit LINEAR; the PVR GBM path has no explicit modifier support).
- `RENDERING|SCANOUT` fails ("create fail") on the render node - card2 is
  render-only; SCANOUT buffers would need a display/primary node.

Implication for pvr_weston: the dmabuf is always implicit-linear XRGB8888, so
Weston's DRM backend can only import it on a plane/output that accepts linear
XRGB8888 (its own GBM/modifier negotiation must not demand an explicit
modifier). If import fails, expect `params_failed` -> no `wl_buffer`.

## Headless weston test result (2026-08-06): NO linux-dmabuf global

Tried to exercise pvr_weston's dmabuf import without taking a real display
(HDMI/USB-C is owned by the running X/gdm session; stealing card0 mid-session
is unsafe). Result:

- weston 9 headless backend only ever loads the **pixman** renderer; it has no
  GL-renderer path (`--renderer=gl` is unhandled; weston.ini `[output]
  renderer=gl` is ignored; gl-renderer.so is only wired up for drm/x11/wayland
  backends). With pixman, the compositor does NOT advertise
  `zwp_linux_dmabuf_v1` -> `pvr_weston` dies at "compositor lacks linux-dmabuf".
- Conclusion: dmabuf import into weston can only be verified on a real output
  (drm-backend on card0-DP-1/HDMI-A-1) once a display is free, or via a nested
  wayland-backend weston hosted inside the running X desktop (headless weston is
  a dead end for this test).

Note: `linux_dmabuf_setup` IS referenced by headless-backend.so but only the
GL renderer path registers the wayland global; pixman path skips it.
