#!/bin/bash
# PA: will the two features Nick wants actually LOAD into the 7.3 Image? vermagic is the gate.
T=/home/host/kernel-trees/host-build/mainline-7.3
echo "=== Image kernel-release string (what vermagic must match) ==="
strings "$T"/arch/arm64/boot/Image | grep -m2 -E '^7\.3\.0-rc2' 
strings "$T"/arch/arm64/boot/Image | grep -m1 'vermagic' 
echo "=== candidate modules ==="
for k in /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/aic8800_fdrv.ko \
         /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/aic8800_bsp.ko \
         "$T"/drivers/gpu/drm/imagination/powervr.ko; do
  if [ -f "$k" ]; then
    printf '%s\n  size=%s mtime=%s\n  vermagic=%s\n' "$k" "$(wc -c <"$k")" \
      "$(ls -l --time-style=+%m-%d_%H:%M:%S "$k" | awk '{print $6}')" \
      "$(modinfo -F vermagic "$k" 2>/dev/null || strings "$k" | grep -m1 '^vermagic=')"
  else echo "MISSING: $k"; fi
done
echo "=== what else is in the 7.3-stage module set ==="
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/ 2>/dev/null | head -20
