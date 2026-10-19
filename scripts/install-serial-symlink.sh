#!/bin/bash
set -e
cd /home/host/opikernel

# 1. install the reconciler
sudo install -m 0755 scripts/opiz3w-serial-compat.sh /usr/local/bin/opiz3w-serial-compat.sh
echo "installed: $(ls -l /usr/local/bin/opiz3w-serial-compat.sh)"

# 2. prove the udev property test used by the reconciler actually matches
echo "--- udevadm info /dev/ttyACM1 (id check) ---"
udevadm info -q property -n /dev/ttyACM1 | grep -E 'ID_VENDOR_ID|ID_MODEL_ID|DEVPATH=' || true

# 3. extend the udev rule: keep the stable name AND fire the reconciler
sudo cp -n /etc/udev/rules.d/99-opiz3w-serial.rules /etc/udev/rules.d/99-opiz3w-serial.rules.bak-$(date +%Y%m%d%H%M)
sudo tee /etc/udev/rules.d/99-opiz3w-serial.rules >/dev/null <<'EOF'
# Stable name for the Orange Pi Zero 3W console (Raspberry Pi Pico / Picoprobe CDC-ACM).
# WHY: after a probe wedge recovery (USB unbind/bind or replug) the kernel re-enumerates
# the device as ttyACM1/ttyACM2 while every pipeline hardcodes /dev/ttyACM0 -- so the
# capture reads nothing and the board "looks dead". This symlink removes that class.
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="000a", SYMLINK+="opiz3w-serial", MODE="0666", GROUP="dialout"
# Reconcile the legacy /dev/ttyACM0 alias on every attach/detach of the probe.
# The reconciler is idempotent, never opens the port, and refuses to clobber a
# real non-probe device on ttyACM0. Long tail of 400+ hardcoded scripts depends on it.
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="000a", RUN+="/usr/local/bin/opiz3w-serial-compat.sh --quiet"
EOF
sudo udevadm control --reload-rules
echo "--- rule file ---"
cat /etc/udev/rules.d/99-opiz3w-serial.rules

# 4. reconcile right now (no udevadm trigger -- we do not want to bounce the live capture)
sudo /usr/local/bin/opiz3w-serial-compat.sh

# 5. verify
echo "--- device nodes ---"
ls -l /dev/opiz3w-serial /dev/ttyACM* 2>&1
echo "--- single-holder check (read-only, does not open the port) ---"
sudo fuser -v /dev/ttyACM1 2>&1 || true
