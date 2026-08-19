# ILI9486 SPI Display Support for Orange Pi Zero 3W


# if the latest commit doesn't work right, that's a big oops on my part. Should have made a stable branch and kept my crazy choices in a beta one. Good thing I'm in a development environment, I would never do that in prod. Just check the previous commits. one of them will work flawlessly, and the DTBO should be unchanged - just GPU implementation will be a mess in the latest version. I am currently working on porting the whole project to a more mainline kernel - but it's taking a very long time to compile because the most convenient machine isn't always the most capable.

Working ILI9486 3.5" SPI TFT (480x320, driven at **2x scale** as a 960x640 framebuffer for faster SPI refresh) (wrong, it's so all the elements from DE fit on display) with XPT2046/ADS7846 touchscreen on the Orange Pi Zero 3W (A733, sun60iw2 / 6.6.98-sun60iw2 vendor kernel).

The module is the standard 3.5" RPi-LCD family (lcdwiki **MPI3501**, "rpi3501"), wired
rev-A on the board's 26-pin header. The display works as a framebuffer console and under
X (fbdev). Touch: software stack is complete and live; 
**Second display**: HDMI (fb0) does not work
## Features

- TinyDRM kernel module (`ili9486` + `drm_mipi_dbi`) — built for 6.6.98-sun60iw2
- DT overlay enables SPI3 and the panel; **2x scale** virtual framebuffer (960x640)
- Framebuffer console on the panel (`fbcon=map:1` in `/boot/orangepiEnv.txt`)
- X11 on the panel via fbdev driver (`10-fbdev-lcd.conf`)
- ADS7846 touch driver with libinput-compatible pressure (`ti,pressure-max=<255>`)
- Backlight: driver is backlight-aware; PWM overlay staged but not enabled (needs wiring, probably not capable but you can add a potentiometer to control amperage to panel LED lines)

## Pin Mapping (rev-A, verified vs Zero 3W schematic pg.17)

| Function | SoC pin | Header | Description |
|----------|---------|--------|-------------|
| SPI3-CS0 | PE0     | 24     | LCD chip select (low active) |
| SPI3-CLK | PE1     | 23     | SPI clock |
| SPI3-MOSI| PE2     | 19     | LCD/TP data in |
| SPI3-MISO| PE3     | 21     | TP data out |
| SPI3-CS1 | PE4     | 26     | Touch chip select (low active) |
| LCD_RS   | PL3     | 18     | Data/Command select |
| RST      | PD0     | 22     | Display reset (optional in driver) |
| TP_IRQ   | PB0     | 11     | Touch interrupt (active-low, pulled up) |
| 3.3V     | -       | 1,17   | Power |
| 5V       | -       | 2,4    | Power |
| GND      | -       | 6,9,14,20,25 | Ground |

**Note**: No backlight pin on the module's 26-pin feed — the LED is rail-powered (always
on). For brightness control see `sun60i-a733-ili9486-backlight.dts` (needs hardware).

## Installation

### 1. Copy files

```bash
# DT overlays
sudo cp sun60i-a733-ili9486.dtbo /boot/dtb/allwinner/overlay/

# Kernel modules
sudo mkdir -p /lib/modules/6.6.98-sun60iw2/extra
sudo cp ili9486.ko drm_mipi_dbi.ko ads7846.ko /lib/modules/6.6.98-sun60iw2/extra/
sudo depmod -a

# X11 config
sudo cp 10-fbdev-lcd.conf /etc/X11/xorg.conf.d/

# Auto-load
sudo cp ili9486.conf /etc/modules-load.d/
```

### 2. Boot config (`/boot/orangepiEnv.txt`)

```
overlays=ili9486
extraargs=fbcon=map:1
```

### 3. Reboot

```bash
sudo reboot
```

## Verification

```bash
lsmod | grep -E "ili9486|ads7846"      # modules loaded
cat /sys/class/drm/card1-SPI-1/status   # connected
ls -la /dev/fb1                          # 1440x960 framebuffer
dmesg | grep -iE "ili9486|ads7846"
cat /proc/bus/input/devices | grep -A6 -i ads7846
```

## Backlight (staged, not enabled)

The driver already hooks `devm_of_find_backlight()` (`source/ili9486.c`), so wiring a
`backlight` DT property drives the standard backlight class. `sun60i-a733-ili9486-backlight.dts`
adds a `pwm-backlight` on **PWM0-0 (PB4, header pin 7)** at 200Hz.

- Header pin 7 = PB4 = PWM0-0 (the only PWM channel on the populated 1-26 range;
  PWM0-1..7 are PD1-PD7, not on the header).
- To enable: `sudo cp sun60i-a733-ili9486-backlight.dtbo /boot/dtb/allwinner/overlay/`
  and add `ili9486-backlight` to `overlays=` in `/boot/orangepiEnv.txt`.
  **Risk**: if the pwm-backlight fails to bind, the ili9486 probe fails (the boot
  watchdog auto-rolls after 3 bad boots).
- Requires hardware: wire pin 7 into the module's backlight feed (e.g. sink PWM via a
  PNP/FET into the LED rail, or lift the module BL jumper). After wiring,
  `/sys/class/backlight/ili9486-bl/brightness` (0-255).

## Touchscreen (XPT2046 / ADS7846)

- Driver: `ads7846` on spi3.1, IRQ 25 (PB0), input event device.
- `ti,pressure-max=<255>` in the DT (or driver fallback) is **required** or libinput
  rejects the device (`min == max on ABS_PRESSURE`). See `source/ads7846.c`.
- Raw probe method (sanity check): `echo spi3.1 > /sys/bus/spi/drivers/ads7846/unbind`,
  then bind `spidev` to spi3.1 and read channels (see `tools/xpt_probe.py`,
  `tools/xpt_dfr.py`, `tools/xpt_corr.py`). Re-binding ads7846 needs a reboot
  (pinctrl IRQ remap bug on this BSP).
- **Protocol (corrected)**: touch X/Y/Z commands MUST be **differential** (SER/DFR=0):
  12-bit X=`0xD0`, Y=`0x90`, Z1=`0xB0`, Z2=`0xC0` (8-bit: X=`0xD8`, Y=`0x98`, Z1=`0xB8`,
  Z2=`0xC8`). The old probe's `0xD4/0x94/0xB4/0xC4` have SER/DFR=1 (single-ended) which
  is wrong for touch and yields frozen mid-scale/0 reads. Aliveness SE channels need
  PD=11 (internal ref on): AUX=`0xE3`, VBAT=`0xA3`, TEMP0=`0x83`, TEMP1=`0xF3`.
- PENIRQ polarity: **active-low** — sits high, pulled low on touch. DT config matches:
  `interrupts = <1 0 8>` (LEVEL_LOW on PB0), `pendown-gpios` ACTIVE_LOW.
- **Status (2026-08-01, corrected — NOT broken glass)**: the XPT2046 chip is alive and
  powered, SPI/MISO works, and the protocol is now verified correct. Distinct real MISO
  patterns per command prove it; `TEMP0` (internal temp diode) settles to a valid ~2046.
  But touch channels X/Y/Z read bit-exact frozen extremes (X=0, Y=2047) with zero
  response to firm press bursts, and PENIRQ never asserts. => the **analog interconnect
  between the resistive film and the XPT2046 is open** (touch FPC / module trace), the
  film itself is fine. Fix: re-seat the touch FPC; if that fails, multimeter continuity
  across each film plate at the FPC pads (~500Ω-2kΩ = film good, isolates fault to module
  PCB). Re-run `tools/xpt_dfr.py` (differential) or `tools/xpt_corr.py` (press-correlation)
  to confirm.
- Note: the sunxi SPI driver rejects spidev clocks below ~200kHz (EINVAL).

## Second/Third Display Options

- card0 = `sunxi-drm` (built-in): DP-1, HDMI-A-1, Writeback-1 — no KMS dumb buffers,
  so X modesetting fails ("dumb interface" unsupported).
- card1 = ili9486 (SPI, fb1). card2 = pvrsrvkm (GPU).
- Zero-hardware second display: use `/dev/fb0` (HDMI legacy framebuffer) for a second
  fbcon / SDL/directfb app.
- Second SPI panel: spi1/spi2/spi4 exist but are disabled and their pins are NOT on
  the 26-pin header (off-header routing needed; spi0 is PC2/3/4/12).
- Kernel rebuild with dumb-buffer support would be needed for X on HDMI.

## Building from Source (`source/`)

```bash
cd source
make -C /lib/modules/$(uname -r)/build M=$PWD modules   # drm_mipi_dbi + ili9486
make -f Makefile.ads7846 -C /lib/modules/$(uname -r)/build M=$PWD modules
sudo cp drm_mipi_dbi.ko ili9486.ko ads7846.ko /lib/modules/6.6.98-sun60iw2/extra/
sudo depmod -a
```

Driver sources here are the **modified** versions used on the board:
- `ili9486.c`: 3x `scale` DT property (virtual 1440x960), `devm_gpiod_get_optional`
  reset, backlight lookup.
- `ads7846.c`: `pressure_max` fallback to 255 if unset (libinput fix).

## Files

| File | Purpose |
|------|---------|
| `sun60i-a733-ili9486.dts/.dtbo` | Current working overlay (rev-A) |
| `sun60i-a733-ili9486-backlight.dts/.dtbo` | Staged pwm-backlight (PWM0-0/pin 7) |
| `ili9486.ko`, `drm_mipi_dbi.ko`, `ads7846.ko` | Live built modules (6.6.98-sun60iw2) |
| `10-fbdev-lcd.conf` | X fbdev config (fb1, 1440x960, Depth 24) |
| `ili9486.conf` | Module auto-load (drm_mipi_dbi, ili9486, ads7846) |
| `pinout ili9486+xpt20xx` | Verified header pinout |
| `source/` | Driver sources + Makefiles |
| `tools/` | `test_ili9486.py` (display), `xpt_probe.py` (touch probe) |

## Troubleshooting

- **No display after overlay**: check `dmesg | grep -iE "ili9486|mipi_dbi|spi3"`.
  A boot-watchdog rolls back after 3 failed boots (see `ili9486-boot-watchdog.sh`
  note in AGENTS.md of the workspace).
- **X fails**: ensure `AutoAddGPU false` and fbdev on `/dev/fb1` are in place; without
  the fbdev config X falls back to modesetting → "dumb interface" error.
- **Touch rejected by libinput**: ensure `ti,pressure-max` present (or use the driver
  fallback build).

## License ( I told it to use the "ching-a-ling" attribution which I made up on the spot, this is what it put)

Provided as-is for educational and personal use. Kernel driver code derives from
Linux (GPL) — see the kernel tree for the original ili9486/drm_mipi_dbi/ads7846 drivers.
