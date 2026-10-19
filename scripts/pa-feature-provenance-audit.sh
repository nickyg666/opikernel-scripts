#!/bin/bash
# PA: where do the two features Nick named actually come from, for a 7.3 build?
echo "=== 1) aic8800: kernel tree has no driver dir; find the real source ==="
T=/home/host/kernel-trees/host-build/mainline-7.3
ls -d "$T"/drivers/net/wireless/* 2>/dev/null | head -20
echo "-- host-wide aic8800 sources (top 12) --"
find /home/host -maxdepth 6 -iname '*aic8800*' -not -path '*/proc/*' 2>/dev/null | head -12
echo "-- aic8800 .ko anywhere on host --"
find /home/host -maxdepth 8 -name 'aic8800*.ko' 2>/dev/null | head -8

echo "=== 2) pvrkms: CONFIG_DRM_POWERVR=m -- does the tree have source + a built .ko? ==="
ls -d "$T"/drivers/gpu/drm/powervr 2>/dev/null || echo "NO drivers/gpu/drm/powervr in tree"
find "$T" -maxdepth 4 -iname '*powervr*' 2>/dev/null | head -8
find "$T" -name 'powervr*.ko' -o -name 'pvrsrvkm*.ko' 2>/dev/null | head -8
echo "-- is it in the git log / where does the symbol come from --"
grep -rn 'DRM_POWERVR' "$T"/drivers/gpu/drm/Kconfig 2>/dev/null | head -3

echo "=== 3) object vs Image timeline (does the stamped Image include the 03:46 pinctrl rebuild?) ==="
ls -l --time-style=+%m-%d_%H:%M:%S "$T"/arch/arm64/boot/Image "$T"/drivers/pinctrl/sunxi/pinctrl-sun60iw2.o "$T"/drivers/pinctrl/sunxi/pinctrl-sunxi-bsp.o "$T"/vmlinux 2>/dev/null
echo "built-in.a bsp member: $(ar t "$T"/drivers/pinctrl/sunxi/built-in.a 2>/dev/null | grep -c bsp)"
