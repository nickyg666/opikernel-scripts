#!/bin/bash
# gpu-core-builtin.sh — put the PowerVR driver and the DRM core helpers it needs
# into the Image, and record every change in the kconfig audit log.
#
# WHY (evidence, board serial 2026-09-30, kernel 7.3.0-rc2-00018-g7dc769e5fbd0-dirty):
#   Board boots to userspace and logs at T+101s:
#     powervr: Unknown symbol drm_gpuva_link (err -2)
#     powervr: Unknown symbol drm_gpuva_unlink (err -2)
#   so modprobe fails, /dev/dri never appears, and there is no render node.
#
#   modinfo -F depends powervr.ko -> gpu-sched,drm_gpuvm,drm_shmem_helper,drm_exec
#   and NONE of those symbols exist in the Image (grep System.map -> 0 hits).
#   The card only ever carried powervr.ko + the aic8800 pair in
#   /lib/modules/<kver>/, so the four dependencies were never on the board.
#
#   THE PART THAT BIT US: you cannot make those four =y on their own.
#   drivers/gpu/drm/imagination/Kconfig does `select DRM_EXEC /
#   DRM_GEM_SHMEM_HELPER / DRM_SCHED / DRM_GPUVM`, and a `select` on a tristate
#   caps the target at the selector's own value. With CONFIG_DRM_POWERVR=m the
#   cap is m, so olddefconfig silently rewrote all four back to m on every run —
#   measured: sed m->y, then olddefconfig, and all four came back =m.
#   Verified decisively: with only CONFIG_DRM_POWERVR=m -> y and NOTHING else
#   forced, olddefconfig keeps powervr=y and all four deps follow to y.
#
#   So the correct lever is the driver itself: =y, built in. That also removes
#   the module entirely from the staging path that has silently regressed before.
set -u
CFG=/home/host/kernel-trees/host-build/mainline-7.3/.config
GOLD=/home/host/opikernel/state/gold.config
AUDIT=/home/host/opikernel/scripts/kconfig-audit.py

# DRM_POWERVR is the lever; the other four are selected by it and are listed only
# so the log shows the full set that moves. The real symbol is
# DRM_GEM_SHMEM_HELPER, not DRM_SHMEM_HELPER — the latter does not exist here.
SYMS="DRM_POWERVR DRM_GPUVM DRM_EXEC DRM_GEM_SHMEM_HELPER DRM_SCHED"
WHY="powervr.ko load-time deps: =m put drm_gpuva_link/unlink + gpu-sched + drm_exec + drm_shmem_helper in modules the board never received, so modprobe died with 'Unknown symbol drm_gpuva_link' and /dev/dri never appeared. DRM_POWERVR=y also lifts the select-cap that made =y on the four deps impossible."

for s in $SYMS; do
  python3 "$AUDIT" set "$s" y -r "$WHY" >/dev/null || exit 1
done

# Write the values into both files. For the four selected symbols this is belt
# and braces: olddefconfig would arrive at the same answer, but writing them means
# the tree and the gold file agree without depending on that.
for f in "$CFG" "$GOLD"; do
  for s in $SYMS; do
    if grep -qE "^CONFIG_${s}=" "$f"; then
      sed -i -E "s/^CONFIG_${s}=[ymn]\$/CONFIG_${s}=y/" "$f"
    else
      echo "MISSING in $f: CONFIG_${s}"
    fi
  done
done

echo "=== .config ==="
grep -nE "^CONFIG_(DRM_POWERVR|DRM_GPUVM|DRM_EXEC|DRM_GEM_SHMEM_HELPER|DRM_SCHED)=" "$CFG"
echo "=== gold.config ==="
grep -nE "^CONFIG_(DRM_POWERVR|DRM_GPUVM|DRM_EXEC|DRM_GEM_SHMEM_HELPER|DRM_SCHED)=" "$GOLD"
echo "=== .config md5 ==="
md5sum "$CFG"