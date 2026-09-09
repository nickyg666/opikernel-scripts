# AGENTS.md — Orange Pi Zero 3W (opikernel) Project

## Project Goals
1. **PVRGL M4** — native Gallium GL driver for PowerVR BXM-4-64 (M2 TQ clear ✅, M3 render ✅, M3.5 geom stream 🔧)
2. Kernel 6.18 stable on opiz3w (A733)
3. Full WiFi + display + GPU stack validated

## Agent Roles

### workflow-organizer
**Responsibilities:** Code sync host↔board, multi-agent coordination, build pipeline orchestration.
- Push files: `cat file | ssh 'cat > path'` (NOT scp — blocked by consent guard)
- Verify pushes: `stat`/`md5sum` on board
- Rebuild: `ninja -C /home/orangepi/mesa26/_build -j2` on board
- Test env: `B=/home/orangepi/mesa26/_build; LD_LIBRARY_PATH=$B/src/egl:$B/src/gbm:$B/src/gallium/targets/dri:$B/src/mesa/glapi/es2api LIBGL_DRIVERS_PATH=$B/src/gallium/targets/dri __EGL_VENDOR_LIBRARY_FILENAMES=/tmp/glvnd/pvrgl_icd.json EGL_PLATFORM=surfaceless`
- Role def: `/home/host/opikernel/workflow-organizer.md`

### py-specialist
**Responsibilities:** Python diagnostic tools, crash log analysis, Python-side testing of GL/EGL harness.
- Board SSH: `sshpass -p orangepi ssh -o StrictHostKeyChecking=accept-new orangepi@192.168.0.151`
- Scripts go in `/home/orangepi/pvrgl-work/` (NOT /tmp — wiped on reboot)

### minecraft-player
**Responsibilities:** Minecraft/PrismLauncher testing, modpack validation, NeoForge diagnostics.
- Minecraft install: `/home/orangepi/minecraft/` (PrismLauncher 11.x, instances 26.1.2 + 26.2)
- Client sync: `curl -sL "https://w8.mom/download/install" -o $TEMP/install-mods.ps1`
- Logs: `/home/orangepi/minecraft/logs/PrismLauncher-*.log`

### network-architect
**Responsibilities:** PVRGL winsys layer, DRM job submission, syncobj/fence handling, geometry/fragment stream pipeline.
- Key files: `pvrgl_tq.c` (transfer queue), `pvrgl_render.c` (render pipeline), `pvrgl_winsys.c` (winsys)
- DRM ioctls: PVR_SUBMIT_JOBS (0x4d), CREATE_CONTEXT, CREATE_BO, VM_MAP
- Syncobj: `syncobj_wait` blocks until fence signaled; `syncobj_reset` clears

### minecraft (broken — DO NOT use)
Returns `HTTP 401: Model ox-alpha-free is not supported`. Use minecraft-player instead.

## CRITICAL BOOT CONSTRAINT
**32-bit U-Boot 2018** — cannot address above `0x43999999`. Every initrd load MUST stay below this ceiling.
- **Kernel**: `0x41000000`
- **Initrd**: `0x45000000` (preferred) or `0x43300000` (August 27 working addr)
- **DTB**: `0x43000000` or `0x44000000`
- **HARD LIMIT**: `0x43999999` — never load anything above this
- Vendor kernel (`/boot/uImage`) has built-in initrd → use `bootm 0x41000000 - 0x43000000` (NO initrd arg)
- Mainline kernel (raw Image) → use `booti 0x41000000 <initrd_addr> <dtb_addr>`
- `saveenv` writes to flash, NOT SD — env not persistent on this card; inline all bootargs per-boot
- tiny-uInitrd too small (1.5MB) — lacks ext4/USB modules → initrd panic. Use full `initrd.img-6.18.19+` (33MB)
- Proven working: `ext4load mmc 0:1 0x41000000 boot/uImage && ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb && bootm 0x41000000 - 0x43000000`

## Lab Topology
- **`.168`** = HOST (HP Pro Mini 400 G9, Ubuntu 26.04) — THE machine you run on. Project root `/home/host/opikernel`.
- **`.151`** = BOARD (opiz3w). SSH orangepi/orangepi. Boots from its own microSD (never visible over USB).
- **`.167`** = WATCHER (Orange Pi Zero 2) — board serial console on ttyS0 @115200 → `/home/orangepi/uart_capture/ttyS0.log`. Quarantined U-Boot interrupters live in `uart_capture_disabled/`.
- **`.149`** = tab (Surface) — ONBOARD SD card reader; board SD mounts as /dev/sda1 → /mnt/sd (sudo pw `1`). Host USB SD reader is BROKEN.
- Board power via Wyze plug "opiz3w": `python3 /home/host/smartplug.py reboot`. Don't cycle power excessively (wears storage).

## Board State
- **IP**: `192.168.0.151`, user/pass `orangepi/orangepi` — **OFFLINE** (needs recovery)
- **Kernel**: `6.18.19+ #N` (mainline), `6.6.98-sun60iw2` (vendor)
- **Mesa tree**: `/home/orangepi/mesa26`, build dir `_build`
- **Host mesa**: `/home/host/mesa-scratch`, branch `pvrgl-m2`
- **GPU**: PowerVR BXM-4-64, render node `/dev/dri/renderD128`
- **WiFi**: AIC8800 SDIO, fixed at 50MHz

## Critical Rules
- **Never kill gateway/hermes-webui** from inside an agent session
- **Never build on board** — cross-compile on host, deploy to board
- **/tmp is volatile** — recreate `glvnd/` + `powervr_dri.so` symlink after every board reboot
- **Board rebuild cap**: `ninja -j2` (never -j8 on board)
- **Verify after push**: `stat` or `md5sum` on board side
- **GitHub PATs**: NEVER print or commit them

## PVRGL Current Status
| Milestone | Status |
|-----------|--------|
| M2 TQ clear | ✅ PASS — `ff 00 00 ff` (blue, BGRA swizzle) |
| M3 render clear (no geom) | ✅ PASS — `ff0000ff` (red) |
| M3.5 geom stream | ✅ FIXED — num_jobs++ before HW schedule; render deadlocks eliminated |
| M4 triangle draw | ⬜ TODO — NIR→pco→USC submission pipeline |


## Collaboration Rule — Delegate to Specialists
**MANDATE: Delegate to other agents when they specialize in the task.** Do not do it yourself if a specialist agent exists — hand off via @mention and track.
- `kernel-architect` / `debugger` / `kconfig-auditor` → kernel/DTS/config/boot validation
- `gpu-driver-expert` → PowerVR / PVRGL / mesa bring-up
- `build-engineer` → kernel/module/mesa builds, deps, deploy
- `TelegramRunner` → cross-chat relay, summaries, obsidian, task diffing, single-source-of-truth docs
- `workflow-organizer` / `py-specialist` → code sync, pipeline, python diagnostics

## Documentation References
| Doc | Location | Notes |
|-----|----------|-------|
| OrangePi Zero3W User Manual v1.0 | `docs/OrangePi_Zero3W_A733_User_Manual_v1.0.pdf` | Board specs, boot modes, GPIO |
| Schematic V1.2 | `docs/OPI_Zero3W_V1.2_Schematic.pdf` | SoC power rails, pinout, peripherals |
| ST7796S Datasheet | `docs/ST7796S_Datasheet.pdf` | SPI display controller |
| Serial Recovery Playbook | `kernel/references/serial-uart-recovery-playbook.md` | Boot recovery state machine |
| PVRGL TQ Clear | `kernel/references/pvrgl-mesa26-tq-clear.md` | TQ backend internals |
| GitHub: nickyg666/orangepi-zero3w-mainline | Remote | 6.18 kernel + DTB sources |
| GitHub: nickyg666/orangepi-zero3w-ili9486-display | Remote | ILI9486 SPI display overlay |

---

# CRITICAL BOOT CONSTRAINT — 32-bit U-Boot 2018
**Board uses U-Boot 2018 (32-bit ARM, NOT ARM64).**
**Violating this constraint causes silent kernel death with no serial output.**

## HARD LIMIT: Cannot address above `0x43999999` in initrd
- Kernel image: `0x41000000` ✅
- Initrd: `0x45000000` (preferred) or `0x43300000` ✅ — must be below `0x43999999`
- DTB: `0x44000000` or `0x43000000` ✅
- Vendor kernel: `bootm 0x41000000 - 0x43000000` (NO initrd arg — vendor uImage has built-in initrd)
- Mainline kernel: `booti 0x41000000 <initrd_addr> <dtb_addr>` — raw Image, NOT uImage
- **NEVER use `bootm` with raw Image** (U-Boot 2018 expects uImage header)
- `saveenv` writes to NAND flash, NOT SD — all bootargs must be inline per-boot
- Bootaddr ceiling: `0x43999999` (some U-Boot builds); use `0x43300000` for safety
- tiny-uInitrd (1.5MB) too small — lacks ext4/USB modules; use full `initrd.img-6.18.19+` (33MB)

## Proven working boot sequence (from `sercap_vendor_repair.log`)
Vendor kernel, SSH reached at ~T+60s:
```
setenv bootargs root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm console=ttyS0,115200
load mmc 0:1 0x41000000 boot/uImage
load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb
bootm 0x41000000 - 0x43000000
```

## Serial Recovery Quick Ref
1. `pkill -f 'cat /dev/ttyACM0'` — free port
2. `lsusb | grep 2e8a` → USB reset if gone
3. Background capture: `sudo setsid bash -c 'exec cat /dev/ttyACM0 >> /home/host/opikernel/pvrgl-work/sercap.log'`
4. Power cycle: `python3 /home/host/smartplug.py off` → wait 8s → `on`
5. Break into U-Boot: send Enter/spaces at ~4.5s post-power
6. Serial logs: host `/home/host/opikernel/pvrgl-work/sercap_go.log`, watcher `.167` `/home/orangepi/uart_capture/ttyS0.log`

## Known failure modes (serial logs)
| Mode | Symptom | Fix |
|------|---------|-----|
| Port contention | Empty log or garbled | `pkill cat` before starting |
| Early exit | Kernel output missed | Background reader survives script exit |
| Garbled bytes | Interleaved stdout/stderr | `strings <log> | grep -v '^$'` |
| aic8800_bt panic | `Unable to handle` at T+17s | `modprobe.blacklist=aic8800_btlpm` in bootargs |

## Serial Recovery Pipeline
**Serial port**: `/dev/ttyACM0` (Picoprobe 2e8a:000a, 115200)
**Recovery playbook**: `/home/host/opikernel/kernel/references/serial-uart-recovery-playbook.md`
**Statehood**: `/home/host/opikernel/kernel/references/serial-recovery-statehood.md`

### Proven boot sequences (U-Boot shell, inline — NO saveenv)
**Vendor kernel** (6.6.98, has built-in initrd):
```
ext4load mmc 0:1 0x41000000 boot/uImage
ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb
bootm 0x41000000 - 0x43000000
```
**Mainline kernel** (6.18.x, full initrd):
```
ext4load mmc 0:1 0x41000000 boot/mainline/Image
ext4load mmc 0:1 0x43300000 boot/mainline/initrd.img-6.18.19+
ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015
fdt addr 0x43000000
fdt resize 65536
setenv bootargs root=PARTUUID=442af407-cb84-48f8-845e-4be5cd18ce13 ro modprobe.blacklist=aic8800_btlpm quiet
booti 0x41000000 - 0x43000000
```

### Critical boot constraint — 32-bit U-Boot 2018
**HARD LIMIT**: U-Boot 2018 (32-bit ARM, not ARM64) cannot address above `0x43999999`.
- **Golden addresses**: kernel `0x41000000`, initrd `0x45000000` (preferred) or `0x43300000`, DTB `0x44000000` or `0x43000000`
- **Initrd ceiling**: `0x43999999` — never load initrd above this
- **tiny-uInitrd** (1.5MB) is too small — missing ext4/USB modules, cannot mount root
- **Full initrd** (`initrd.img-6.18.19+`, 33MB) required — use `0x45000000` or `0x43300000`
- `saveenv` writes to flash, NOT SD — all bootargs must be set inline per-boot
- **vendor `uImage`** boots with `bootm` (no initrd arg — built-in); mainline **raw `Image`** boots with `booti`
- Break at ~4500ms post-power-on; drain stale buffer before sending commands
- **aic8800_bt** panic at T+17s — `modprobe.blacklist=aic8800_btlpm` in bootargs fixes it

### Serial failure modes (use `strings` to verify logs)
1. **Port held by competing `cat`** → `pkill -f 'cat /dev/ttyACM0'` before starting
2. **Script exits before kernel output** → long-running background capture
3. **Garbled/interleaved bytes** → `strings <log> | grep -c <known-phrase>` to verify content is intact
## Documentation
- User Manual: `docs/OrangePi_Zero3W_A733_User_Manual_v1.0.pdf`
- Schematic: `docs/OPI_Zero3W_V1.2_Schematic.pdf`
- ST7796S display: `docs/ST7796S_Datasheet.pdf`
- Serial recovery: `kernel/references/serial-uart-recovery-playbook.md` + `kernel/references/serial-fixing-statehood.md`

### kernel-architect
**Responsibilities:** Ensure kernel modules and builds will be interoperable with the help of debugger, auditors and others. Rewrite this every 50 turns to keep it relevant.
- Validate kernel/module interop: confirm all exported symbols resolve, no ABI drift between build configs
- Kconfig audit: verify `CONFIG_*` flags are consistent between defconfig and board .config
- DTB/DTBO changes: verify bootability before deployment (check magic numbers, size deltas, compile from source)
- Dependency chain: kernel → modules → userspace libs must be version-matched
- Reference: `kernel/references/serial-uart-recovery-playbook.md` for boot-level fixes
- Rewrite role definition every 50 turns or when project scope changes significantly
