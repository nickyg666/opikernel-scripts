#!/usr/bin/env bash
# Strip every remote-desktop / VNC / X-server unit from an opiz3w rootfs.
#
# WHY: this board has LOCAL HDMI displays. The VNC stack (opiz3w-novnc,
# opiz3w-x11vnc, xvfb-virtual-display, Xorg/Xvfb, gdm) was added by an earlier
# session for a remote-desktop path that was never wanted. It is also the unit
# set that produced the original "graphical.target ordering cycle" and the
# 117-second hold on multi-user.target.
#
# Everything here is optional for a headless serial board: device nodes come from
# devtmpfs, not from udev rule-driven X probing.
#
# Usage: sudo bash strip-remote-desktop.sh /mnt/target
set -euo pipefail

M="${1:?usage: strip-remote-desktop.sh <mountpoint>}"
TS="$(date +%Y%m%d-%H%M%S)"

[ -d "$M/etc/systemd/system" ] || { echo "FAIL: $M is not an opiz3w rootfs"; exit 1; }

# Everything we remove: VNC, Xvfb, Xorg, the GDM/display-manager path.
PATTERNS='novnc|x11vnc|opiz3w-novnc|opiz3w-x11vnc|xvfb|xvfb-virtual|gdm|lightdm|sddm|display-manager|x11-common|x11-xserver-utils'

echo "=== before ==="
find "$M/etc/systemd/system" -maxdepth 2 -lname '*' 2>/dev/null \
  | grep -iE "$PATTERNS" | sed "s|$M||" | head -20 || true
BEFORE=$(find "$M/etc/systemd/system" -maxdepth 2 -lname '*' 2>/dev/null | grep -ciE "$PATTERNS" || echo 0)
echo "  matching symlinks/units: $BEFORE"

echo "=== 1. unlink every wants/ symlink that pulls in the stack ==="
REMOVED=0
while read -r link; do
  [ -z "$link" ] && continue
  echo "  unlink ${link#$M}"
  rm -f "$link"
  REMOVED=$((REMOVED+1))
done < <(find "$M/etc/systemd/system" -maxdepth 2 -type l 2>/dev/null | grep -iE "$PATTERNS")

echo "=== 2. remove default.target -> graphical.target (no display manager here) ==="
DEF="$M/lib/systemd/system/default.target"
if [ -L "$DEF" ]; then
  if [ "$(readlink -f "$DEF")" != "$(readlink -f "$M/usr/lib/systemd/system/multi-user.target")" ]; then
    cp -p "$DEF" "$DEF.bak-$TS" 2>/dev/null || true
    rm -f "$DEF"
    ln -s multi-user.target "$DEF"
    echo "  default.target -> multi-user.target (old kept as default.target.bak-$TS)"
  else
    echo "  already multi-user.target"
  fi
fi

echo "=== 3. mask the units outright, so nothing pulls them back in ==="
mkdir -p "$M/etc/systemd/system"
for u in opiz3w-novnc.service opiz3w-x11vnc.service xvfb-virtual-display.service \
         gdm.service display-manager.service systemd-networkd-wait-online.service; do
  if [ -f "$M/lib/systemd/system/$u" ] || [ -f "$M/etc/systemd/system/$u" ]; then
    rm -f "$M/etc/systemd/system/$u"
    ln -s /dev/null "$M/etc/systemd/system/$u"
    echo "  masked $u"
  fi
done

sync

echo "=== after ==="
AFTER=$(find "$M/etc/systemd/system" -maxdepth 2 -type l 2>/dev/null | grep -ciE "$PATTERNS" || echo 0)
echo "  matching symlinks: $AFTER"
echo "  default.target -> $(readlink -f "$DEF")"
echo "  unlinked: $REMOVED"
echo
echo "Done. Reboot; expect a login prompt with no VNC/X in the path."