#!/bin/bash
# Stage the current 7.3 build onto a mounted card. Idempotent, identity-gated,
# backs up before overwriting, and verifies by readback. Nick's rule: never
# infer which card is which from lsblk alone - print the identity, not a guess.
set -euo pipefail
M="${1:?usage: stage-7.3-to-card.sh <mountpoint>}"
K=/home/host/kernel-trees/host-build/mainline-7.3
REL=7.3.0-rc2-00018-g7dc769e5fbd0-dirty
TS="$(date +%Y%m%d-%H%M%S)"

[ -f "$M/boot/mainline/Image" ] || { echo "FAIL: $M has no boot/mainline/Image"; exit 1; }

echo "=== IDENTITY OF TARGET (do not assume) ==="
df -h "$M" | tail -1
echo -n "current Image on card : "; md5sum "$M/boot/mainline/Image" | cut -d' ' -f1
echo -n "build tree Image      : "; md5sum "$K/arch/arm64/boot/Image" | cut -d' ' -f1

for f in boot/mainline/Image boot/mainline/sun60i-a733-orangepi-zero3w.dtb \
         "lib/modules/$REL/aic8800_bsp.ko" "lib/modules/$REL/aic8800_fdrv.ko"; do
  [ -f "$M/$f" ] && sudo cp -p "$M/$f" "$M/$f.bak-$TS"
done
sudo cp -f "$K/arch/arm64/boot/Image"                          "$M/boot/mainline/Image"
sudo cp -f "$K/arch/arm64/boot/dts/allwinner/sun60i-a733-orangepi-zero3w.dtb" \
                                                          "$M/boot/mainline/"
sudo cp -f "$K/drivers/net/wireless/aic8800/aic8800_bsp/aic8800_bsp.ko"                                                           "$M/lib/modules/$REL/"
sudo cp -f "$K/drivers/net/wireless/aic8800/aic8800_fdrv/aic8800_fdrv.ko"                                                           "$M/lib/modules/$REL/"
sync

echo "=== READBACK VERIFY ==="
fail=0
for p in "boot/mainline/Image:arch/arm64/boot/Image" \
         "boot/mainline/sun60i-a733-orangepi-zero3w.dtb:arch/arm64/boot/dts/allwinner/sun60i-a733-orangepi-zero3w.dtb" \
         "lib/modules/$REL/aic8800_bsp.ko:drivers/net/wireless/aic8800/aic8800_bsp/aic8800_bsp.ko" \
         "lib/modules/$REL/aic8800_fdrv.ko:drivers/net/wireless/aic8800/aic8800_fdrv/aic8800_fdrv.ko"; do
  cf="${p%%:*}"; hf="${p##*:}"
  c=$(sudo md5sum "$M/$cf" | cut -d' ' -f1); h=$(md5sum "$K/$hf" | cut -d' ' -f1)
  if [ "$c" = "$h" ]; then echo "OK   $c  $(basename "$cf")"; else echo "FAIL $c != $h"; fail=1; fi
done
echo "=== magic + vermagic ==="
echo -n "Image magic: "; sudo xxd -p -l4 "$M/boot/mainline/Image"
modinfo -F vermagic "$M/lib/modules/$REL/aic8800_fdrv.ko"
[ $fail -eq 0 ] && echo "STAGED CLEANLY (backups .bak-$TS)" || exit 1
