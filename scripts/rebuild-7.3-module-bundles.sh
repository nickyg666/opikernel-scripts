#!/bin/bash
# rebuild-7.3-module-bundles.sh — regenerate the 7.3 deploy module bundles from the CURRENT build tree
# so the published Image and its modules always ship as one coherent set.
#
#   modules-small-va39.tar.gz : flat curated set (15 .ko + firmware/powervr/ + first-boot.sh) for first-boot bring-up
#   modules-va39.tar.gz       : full lib/modules/<vermagic>/ tree from `make modules_install INSTALL_MOD_STRIP=1`
#
# In-tree modules are stripped with the SAME command kbuild uses for INSTALL_MOD_STRIP=1
# ($(CROSS_COMPILE)strip --strip-debug), so a bundle ko is byte-identical to a modules_install copy.
# The out-of-tree aic8800 modules are NOT rebuilt here (their vermagic must be checked separately).
#
# Usage: scripts/rebuild-7.3-module-bundles.sh [--small-only|--full-only] [--force]
set -euo pipefail

KDIR=${KDIR:-/home/host/kernel-trees/host-build/mainline-7.3}
DEPLOY=${DEPLOY:-/home/host/opikernel/stage/7.3-stage/deploy-va39}
STAGE=${STAGE:-/home/host/opikernel/stage/7.3-stage}
CROSS=${CROSS_COMPILE:-aarch64-linux-gnu-}
STRIP=${CROSS}strip
JOBS=${JOBS:-8}
STAMP=$(date +%Y%m%d-%H%M%S)
MODE=both; FORCE=0
for a in "$@"; do case "$a" in --small-only) MODE=small;; --full-only) MODE=full;; --force) FORCE=1;; esac; done

# in-tree modules for the flat small bundle: basename -> path under KDIR
declare -A SRC=(
  [drm.ko]=drivers/gpu/drm/drm.ko
  [drm_exec.ko]=drivers/gpu/drm/drm_exec.ko
  [drm_gpuvm.ko]=drivers/gpu/drm/drm_gpuvm.ko
  [drm_kms_helper.ko]=drivers/gpu/drm/drm_kms_helper.ko
  [drm_shmem_helper.ko]=drivers/gpu/drm/drm_shmem_helper.ko
  [drm_panel_orientation_quirks.ko]=drivers/gpu/drm/drm_panel_orientation_quirks.ko
  [gpu-sched.ko]=drivers/gpu/drm/scheduler/gpu-sched.ko
  [powervr.ko]=drivers/gpu/drm/imagination/powervr.ko
  [backlight.ko]=drivers/video/backlight/backlight.ko
  [cfg80211.ko]=net/wireless/cfg80211.ko
  [mac80211.ko]=net/mac80211/mac80211.ko
  [rfkill.ko]=net/rfkill/rfkill.ko
  [libarc4.ko]=lib/crypto/libarc4.ko
)
OOT=(aic8800_fdrv.ko aic_load_fw.ko)

say() { printf '%s\n' "$*"; }
die() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }

[ -d "$KDIR" ] || die "no KDIR $KDIR"
[ -d "$DEPLOY" ] || die "no DEPLOY $DEPLOY"
if [ "$FORCE" = 0 ] && [ "$(pgrep -x make | wc -l)" != 0 ]; then
  die "a build is running (pgrep -x make) — bundles would mix a stale tree with a fresh Image (use --force)"
fi
REL=$(cat "$KDIR/include/config/kernel.release")
say "KDIR=$KDIR  release=$REL  stamp=$STAMP"

# ---------- small bundle ----------
if [ "$MODE" != full ]; then
  SMALL="$DEPLOY/small-$STAMP"; rm -rf "$SMALL"; mkdir -p "$SMALL/firmware"
  for k in "${!SRC[@]}"; do
    f="$KDIR/${SRC[$k]}"
    [ -f "$f" ] || die "missing $f"
    "$STRIP" --strip-debug -o "$SMALL/$k" "$f"
  done
  for k in "${OOT[@]}"; do
    if [ -f "$KDIR/$k" ]; then cp "$KDIR/$k" "$SMALL/$k";           # in-tree build of aic8800
    elif [ -f "$DEPLOY/small/$k" ]; then cp "$DEPLOY/small/$k" "$SMALL/$k"
    else die "no source for out-of-tree $k"; fi
  done
  # firmware stays FLAT at ./firmware/*.fw on purpose: the bundle's own first-boot.sh does
  # `mkdir -p /lib/firmware/powervr && cp $D/firmware/*.fw /lib/firmware/powervr/` (line 6).
  # Nesting it to firmware/powervr/ here breaks that glob and the module probes nothing.
  cp "$DEPLOY"/firmware/*.fw "$SMALL/firmware/" 2>/dev/null || say "WARN: no firmware/*.fw to copy"
  [ -f "$DEPLOY/first-boot.sh" ] && cp "$DEPLOY/first-boot.sh" "$SMALL/"
  if [ -f "$DEPLOY/modules-small-va39.tar.gz" ]; then cp -p "$DEPLOY/modules-small-va39.tar.gz" "$DEPLOY/modules-small-va39.tar.gz.bak-$STAMP"; fi
  tar czf "$DEPLOY/modules-small-va39.tar.gz" -C "$SMALL" .
  say "small: $(stat -c%s "$DEPLOY/modules-small-va39.tar.gz") B  entries=$(tar tzf "$DEPLOY/modules-small-va39.tar.gz" | wc -l)  staging=$SMALL"
fi

# ---------- full bundle ----------
if [ "$MODE" != small ]; then
  FULL=${FULL:-$STAGE/mods-full-$STAMP}
  if [ -d "$FULL/lib/modules/$REL" ]; then
    say "full: reusing existing install tree $FULL"
  else
    rm -rf "$FULL"; mkdir -p "$FULL"
    say "full: make modules_install -> $FULL (this takes a few minutes)"
    nice -n 10 make -C "$KDIR" ARCH=arm64 CROSS_COMPILE="$CROSS" -j"$JOBS" \
      INSTALL_MOD_PATH="$FULL" INSTALL_MOD_STRIP=1 DEPMOD=true modules_install >"${LOG:-/home/host/opikernel/pvrgl-work/mods-install-$STAMP.log}" 2>&1 \
      || die "modules_install failed, see ${LOG:-/home/host/opikernel/pvrgl-work/mods-install-$STAMP.log}"
  fi
  [ -d "$FULL/lib/modules/$REL" ] || die "no $FULL/lib/modules/$REL after install"
  # the deploy bundle is a superset of the install tree: depmod outputs, the out-of-tree aic8800
  # modules and the PowerVR firmware live alongside lib/ (this is how the 2026-09-15 bundle was
  # assembled — dropping them silently would leave a bundle whose modprobe deps do not resolve
  # and whose WiFi/GPU firmware is absent)
  if command -v depmod >/dev/null; then
    depmod -b "$FULL" -a "$REL" && say "full:  depmod -b $FULL -a $REL OK"
  else
    say "WARN: no host depmod — modules.dep will be missing from the bundle"
  fi
  if [ -f "$DEPLOY/modules-va39.tar.gz.bak-$STAMP" ]; then
    OLD="$DEPLOY/modules-va39.tar.gz.bak-$STAMP"
  else
    OLD=$(ls -1t "$DEPLOY"/modules-va39.tar.gz.bak-* 2>/dev/null | head -1)
  fi
  if [ -n "${OLD:-}" ] && [ -f "$OLD" ]; then
    tar xzf "$OLD" -C "$FULL" firmware modules/aic8800_fdrv.ko modules/aic_load_fw.ko 2>/dev/null \
      && say "full:  carried over firmware/ + modules/aic*.ko from $(basename "$OLD")" \
      || say "WARN: no firmware/aic payload in $(basename "$OLD")"
  fi
  if [ -f "$DEPLOY/modules-va39.tar.gz" ]; then cp -p "$DEPLOY/modules-va39.tar.gz" "$DEPLOY/modules-va39.tar.gz.bak-$STAMP"; fi
  MEMBERS="lib"
  [ -d "$FULL/firmware" ] && MEMBERS="$MEMBERS firmware"
  [ -d "$FULL/modules" ] && MEMBERS="$MEMBERS modules"
  tar czf "$DEPLOY/modules-va39.tar.gz" -C "$FULL" $MEMBERS
  say "full:  $(stat -c%s "$DEPLOY/modules-va39.tar.gz") B  entries=$(tar tzf "$DEPLOY/modules-va39.tar.gz" | wc -l)"
fi

# ---------- verify both bundles carry THIS build's powervr.ko ----------
PV="$KDIR/drivers/gpu/drm/imagination/powervr.ko"
RAW=$(md5sum "$PV" | cut -d' ' -f1)
"$STRIP" --strip-debug -o /tmp/.pv-ref-$STAMP.ko "$PV"
STR=$(md5sum /tmp/.pv-ref-$STAMP.ko | cut -d' ' -f1); rm -f /tmp/.pv-ref-$STAMP.ko
say "reference powervr.ko raw=$RAW stripped=$STR"
rc=0
for b in modules-small-va39.tar.gz modules-va39.tar.gz; do
  p="$DEPLOY/$b"; [ -f "$p" ] || continue
  got=$(tar xzOf "$p" --wildcards '*powervr.ko' 2>/dev/null | md5sum | cut -d' ' -f1)
  case "$got" in
    "$RAW") v="match(raw)";;
    "$STR") v="match(stripped)";;
    *)      v="STALE"; rc=1;;
  esac
  say "VERIFY $b powervr.ko=$got $v  tar_md5=$(md5sum "$p" | cut -d' ' -f1)"
done
say "BUNDLES $STAMP $( [ $rc = 0 ] && echo OK || echo STALE )"
exit $rc
