#!/bin/bash
# PA bounded audit: does the LIVE 7.3 .config carry the features Nick named
# (SDIO aic8800, pvrkms/PowerVR DRM, plus the boot-blocking pinctrl gate)?
T=/home/host/kernel-trees/host-build/mainline-7.3
cd "$T" || { echo "NO TREE $T"; exit 1; }
echo "TREE=$T  NOW=$(date +%m-%d_%H:%M:%S)"
echo "CONFIG_MD5=$(md5sum .config | cut -d' ' -f1)  SIZE=$(wc -c < .config)  MTIME=$(ls -l --time-style=+%m-%d_%H:%M:%S .config | awk '{print $6}')"
head -3 .config

echo "--- CONFIG HEADER (arch check) ---"
grep -E '^CONFIG_(ARM64|ARCH_SUNXI|PINCTRL_SUNXI|PINCTRL_SUN60IW2)=' .config

echo "--- REQUESTED FEATURES (exact symbols) ---"
for s in AIC8800 AIC8800_SDIO AIC8800_USB AIC8800_BTLPM AIC8800_SDIO_BT \
         MMC_SUNXI MMC_SUNXI_SUN60I DRM_PVR DRM_POWERVR PVR_KMS PVR_ROGUE \
         DRM_SUN4I DRM_SUN8I_DW_HDMI SUNXI_DRM VIDEO_SUNXI_HDMI; do
  hit=$(grep -E "^CONFIG_${s}=" .config | head -1)
  printf '%-22s %s\n' "$s" "${hit:-<absent>}"
done

echo "--- FUZZY: any symbol mentioning the features ---"
grep -nEi '^(CONFIG_.*(AIC8800|PWRVR|POWERVR|PVR).*(=y|=m))' .config | head -25
echo "(count: $(grep -cEi '^CONFIG_.*(AIC8800|POWERVR|PVR)' .config))"

echo "--- BUILT ARTIFACT: is the aic8800 driver actually in the tree/build? ---"
ls -l --time-style=+%m-%d_%H:%M:%S drivers/net/wireless/aic8800 2>/dev/null | head -5
find . -name 'aic8800*' -maxdepth 4 -type d 2>/dev/null | head -5
echo "--- pinctrl bsp object state ---"
ls -l --time-style=+%m-%d_%H:%M:%S drivers/pinctrl/sunxi/pinctrl-sunxi-bsp.c drivers/pinctrl/sunxi/*sun60iw2* 2>/dev/null | head -8
ar t drivers/pinctrl/sunxi/built-in.a 2>/dev/null | grep -i -E 'bsp|sun60iw2' | head -5
