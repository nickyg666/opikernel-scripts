#!/usr/bin/env bash
# getty-fix.sh — make a mounted opiz3w rootfs give us a serial shell and SSH.
#
# WHY: the stock card has
#     lib/systemd/system/default.target -> graphical.target
#   but NO display manager is installed, and graphical.target has
#     Wants=display-manager.service
# so the boot can never complete graphical.target, and getty.target (ordered
# after it) never runs -> no serial getty, no SSH, board goes silent at ~16s.
# The getty units themselves are correct and are NOT touched.
#
# IDENTITY RULE: never decide which card this is from size, LABEL, PARTUUID or
# hostname. Several cards share LABEL=opi_root and even an ext4 UUID. Run this
# against a card you have ALREADY identified by artifact MD5.
#
# Usage: sudo bash getty-fix.sh /mnt/target [expected Image md5]
set -euo pipefail

M="${1:?usage: getty-fix.sh <mountpoint> [expected-Image-md5]}"
REL="7.3.0-rc2-00018-g7dc769e5fbd0-dirty"
TS="$(date +%Y%m%d-%H%M%S)"

[ -d "$M/lib/systemd/system" ] || { echo "FAIL: $M is not an opiz3w rootfs"; exit 1; }

echo "=== card: $M ==="
echo "--- identity by artifact MD5 (never trust size/label) ---"
for f in boot/mainline/Image boot/mainline/sun60i-a733-orangepi-zero3w.dtb; do
  [ -f "$M/$f" ] && echo "$(md5sum "$M/$f" | cut -d' ' -f1)  $f" || echo "MISSING  $f"
done
for m in aic8800_bsp aic8800_fdrv; do
  f="$M/lib/modules/$REL/$m.ko"
  [ -f "$f" ] && echo "$(md5sum "$f" | cut -d' ' -f1)  $m.ko" || echo "MISSING  $m.ko"
done
if [ $# -ge 2 ]; then
  got="$(md5sum "$M/boot/mainline/Image" | cut -d' ' -f1)"
  [ "$got" = "$2" ] || { echo "FAIL: Image md5 $got != expected $2 - wrong card?"; exit 1; }
  echo "Image md5 matches expected."
fi
df -h "$M" | tail -1

echo
echo "--- BEFORE ---"
echo "default.target -> $(readlink -f "$M/lib/systemd/system/default.target")"
ls "$M/etc/systemd/system/multi-user.target.wants/" 2>/dev/null | grep -ix ssh.service \
  || echo "ssh.service: not enabled"

echo
echo "--- APPLY ---"
# 1. default.target: graphical -> multi-user (back up first, always)
if [ "$(readlink -f "$M/lib/systemd/system/default.target")" != "$(readlink -f "$M/usr/lib/systemd/system/multi-user.target")" ]; then
  cp -p "$M/lib/systemd/system/default.target" \
        "$M/lib/systemd/system/default.target.bak-$TS"
  rm -f "$M/lib/systemd/system/default.target"
  ln -s multi-user.target "$M/lib/systemd/system/default.target"
  echo "default.target -> multi-user.target (old kept as default.target.bak-$TS)"
else
  echo "default.target already multi-user.target"
fi

# 2. enable sshd: it is installed but was never enabled, which is why the board
#    never answered on the network.
W="$M/etc/systemd/system/multi-user.target.wants"
mkdir -p "$W"
if [ -f "$M/usr/sbin/sshd" ]; then
  ln -sf /lib/systemd/system/ssh.service "$W/ssh.service"
  echo "ssh.service enabled (sshd binary present: $($M/usr/sbin/sshd -V 2>&1 | head -1))"
else
  echo "WARNING: no sshd binary on this card - skipping ssh enable"
fi

# 3. make sure the serial getty is in multi-user.wants too, not only
#    getty.target.wants, so it cannot be lost to a target change again.
ln -sf /lib/systemd/system/serial-getty@ttyS0.service "$W/serial-getty@ttyS0.service"
echo "serial-getty@ttyS0 present in multi-user.target.wants"

sync

echo
echo "--- AFTER (verify on the card, not in this script) ---"
echo "default.target -> $(readlink -f "$M/lib/systemd/system/default.target")"
ls -l "$W/ssh.service" "$W/serial-getty@ttyS0.service"
echo
echo "Expect after boot: autologin shell on ttyS0 AND working ssh."
