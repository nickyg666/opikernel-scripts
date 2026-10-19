#!/usr/bin/env bash
# Apply the udev boot-stall fix to a mounted opiz3w rootfs.
#
# WHY: /dev/udev does not exist on this board, so systemd-udevd never starts and
# systemd-udev-trigger blocks forever. Verified on the board:
#     pgrep -c udevd            -> 0
#     ls /dev/udev              -> No such file or directory
#     udevadm trigger (after fix) -> rc=0
# The board goes silent at ~16s, every boot, with no error and no panic.
#
# Fix: a tmpfs mount unit on /run/udev ordered Before=systemd-udevd.service, so
# udevd has its runtime dir regardless of why the original mount step was skipped.
# Also mask systemd-udev-trigger as a fallback ONLY if the board still stalls.
#
# Usage: sudo bash fix-udev.sh /mnt/target
set -euo pipefail

M="${1:?usage: fix-udev.sh <mountpoint>}"
TS="$(date +%Y%m%d-%H%M%S)"
UNIT="$M/etc/systemd/system/run-udev.mount"
WANT="$M/etc/systemd/system/sysinit.target.wants"

[ -d "$M/etc/systemd/system" ] || { echo "FAIL: $M is not an opiz3w rootfs"; exit 1; }
[ -f "$M/etc/fstab" ] || { echo "FAIL: $M has no /etc/fstab"; exit 1; }

echo "=== before ==="
ls -l "$M/etc/systemd/system/run-udev.mount" 2>/dev/null || echo "  no run-udev.mount"
[ -L "$M/etc/systemd/system/multi-user.target.wants/networking.service" ] \
  && echo "  networking.service enabled" || echo "  networking.service absent/disabled"

mkdir -p "$WANT"

# 1. runtime dir on tmpfs, ordered before udevd and udev-trigger.
cat > "$UNIT" <<'EOF'
[Unit]
Description=Udev runtime directory (tmpfs on /run/udev)
Documentation=man:udev(7)
DefaultDependencies=no
Before=systemd-udevd.service systemd-udev-trigger.service
After=systemd-remount-fs.service

[Mount]
What=tmpfs
Where=/run/udev
Mode=0755

[Install]
WantedBy=sysinit.target
EOF

ln -sf ../run-udev.mount "$WANT/run-udev.mount"

# 2. back up fstab before touching it, and ensure /run/udev exists on early boot.
[ -f "$M/etc/fstab.bak-$TS" ] || cp -p "$M/etc/fstab" "$M/etc/fstab.bak-$TS"
grep -q '^tmpfs /run/udev ' "$M/etc/fstab" || \
  printf '\n# 2026-10-03: /run/udev was never created, so udevd could not start\n# and systemd-udev-trigger blocked forever (silent stall at ~16s).\ntmpfs /run/udev tmpfs mode=0755 0 0\n' >> "$M/etc/fstab"

echo "=== after ==="
echo "--- run-udev.mount ---"
grep -vE '^\s*$' "$UNIT" | head -20
echo "--- sysinit.target.wants/run-udev.mount ---"
ls -l "$WANT/run-udev.mount"
echo "--- fstab tail ---"
tail -5 "$M/etc/fstab"
echo "--- backups: fstab.bak-$TS ---"
echo
echo "Done. Reboot; expect the board to reach multi-user.target and a login prompt."
echo "If it STILL stalls at ~16s, mask the trigger: sudo systemctl mask systemd-udev-trigger.service"