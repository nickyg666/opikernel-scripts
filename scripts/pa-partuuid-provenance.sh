#!/bin/bash
# PA: which card/PARTUUID does each artifact belong to? + mmc node status in DTB source
cd /home/host/opikernel || exit 1
echo "== who references each PARTUUID =="
for u in 486ea4ae 442af407; do
  echo "--- $u"
  grep -rl "$u" --include='*' -I . 2>/dev/null | grep -v '^./pvrgl-work/sercap' | head -12
done
echo "== boot.scr / bootargs sources =="
find . -maxdepth 5 \( -name 'boot.scr*' -o -name '*.scr' \) -newermt '2026-09-01' 2>/dev/null | head
echo "== dts source tree with sun60iw2 =="
find /home/host -maxdepth 6 -name 'sun60iw2*.dtsi' 2>/dev/null | head -6
echo "== mmc node status in those dtsi =="
for f in $(find /home/host -maxdepth 6 -name 'sun60iw2*.dtsi' 2>/dev/null | head -3); do
  echo "--- $f"
  grep -n -A6 -E 'mmc0:|sdc0:|sdmmc0:' "$f" 2>/dev/null | head -30
done
