#!/bin/bash
# PA: is an SD/MMC host driver even enabled in the 7.3 config?
echo "== find build .config / gold.config =="
ls -l --time-style=+%m-%d_%H:%M:%S /tmp/gold.config 2>/dev/null
find /home/host/opikernel -maxdepth 4 -name '.config' -newermt '2026-09-15' 2>/dev/null | head -10
K=$(find /home/host/opikernel -maxdepth 4 -name '.config' -newermt '2026-09-15' 2>/dev/null | head -1)
echo "K=$K"
echo "== MMC/SD host config =="
for f in /tmp/gold.config "$K"; do
  [ -f "$f" ] || continue
  echo "--- $f"
  grep -E '^CONFIG_(MMC|MMC_SUNXI|MMC_SDHCI|MMC_BLOCK|MMC_BLOCK_MINORS|PINCTRL_SUN60IW2|PINCTRL_SUNXI|DRM_POWERVR|DRM_IMAGINATION)[=y m]' "$f"
done
echo "== DTS: mmc nodes in the built DTB source =="
grep -rn 'mmc0\|sdc0\|sdmmc' /home/host/opikernel/linux*/arch/arm64/boot/dts/allwinner/sun60iw2*.dtsi 2>/dev/null | head -10
