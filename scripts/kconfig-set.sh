#!/usr/bin/env bash
# Set a Kconfig symbol the way kdir-build.sh will actually honour it.
#
# Why this exists: kdir-build.sh reads gold from /tmp/gold.config and restores
# .config from it (plus a stable stamp) whenever they disagree. A `.config`-only
# edit is therefore silently reverted, and the build then produces a
# byte-identical Image while reporting rc=0. That cost two full builds on
# 2026-09-28 before the build script was fixed to shout about it.
#
# This writes the symbol to BOTH the real gold and the tree .config, and clears
# the stable stamp, which is the only combination that survives the guard.
# Then it tells you how to verify the change actually landed.
#
#   kconfig-set.sh CONFIG_AW_RFKILL y
#   kconfig-set.sh CONFIG_DRM_FBDEV_EMULATION n
#   kconfig-set.sh --show CONFIG_AW_RFKILL
set -euo pipefail

KDIR="${KDIR:-/home/host/kernel-trees/host-build/mainline-7.3}"
GOLD="${GOLD:-/home/host/opikernel/state/gold.config}"
STAMP="${STAMP:-/home/host/opikernel/state/builds/.config.stable.md5}"
CFG="$KDIR/.config"

usage() { sed -n '2,20p' "$0"; exit 64; }
[ $# -ge 1 ] || usage

set_in_file() { # $1=file $2=key $3=value
  local f=$1 k=$2 v=$3
  if grep -q "^$k=" "$f" 2>/dev/null; then
    sed -i "s/^$k=.*/$k=$v/" "$f"
  elif grep -q "^# $k is not set" "$f" 2>/dev/null; then
    if [ "$v" = "n" ]; then
      sed -i "s/^# $k is not set$/$k/" "$f"   # keep as not-set
    else
      sed -i "s/^# $k is not set$/$k=$v/" "$f"
    fi
  else
    printf '%s=%s\n' "$k" "$v" >>"$f"
  fi
}

if [ "$1" = "--show" ]; then
  k=$2
  printf 'gold : %s\n' "$(grep -E "^($k=|# $k is not set)" "$GOLD" 2>/dev/null || echo '(absent)')"
  printf 'config: %s\n' "$(grep -E "^($k=|# $k is not set)" "$CFG"  2>/dev/null || echo '(absent)')"
  printf 'note : the build uses %s\n' "$GOLD"
  exit 0
fi

[ $# -eq 2 ] || usage
key=$1
val=$2
case "$val" in
  y|m) ;;
  n) val=n ;;
  *) echo "value must be y, m or n (got '$val')" >&2; exit 64 ;;
esac

[ -f "$GOLD" ] || { echo "gold config missing: $GOLD" >&2; exit 1; }
[ -f "$CFG" ]  || { echo "tree .config missing: $CFG" >&2; exit 1; }

before_gold=$(md5sum "$GOLD" | cut -d' ' -f1)

# Record the intent BEFORE touching anything. kdir-build.sh reads this log to
# decide whether a .config/gold divergence is deliberate, so the entry has to
# exist first or the build would flag the change as undeclared drift.
AUDIT_CLI="$(dirname "$0")/kconfig-audit.py"
if [ -x "$AUDIT_CLI" ]; then
  "$AUDIT_CLI" set "$key" "$val" -r "${REASON:-applied via kconfig-set.sh}" || true
fi

set_in_file "$GOLD" "$key" "$val"
set_in_file "$CFG"  "$key" "$val"
rm -f "$STAMP"

echo "set $key=$val"
echo "  gold  $GOLD"
echo "  .config $CFG"
echo "  stamp cleared ($STAMP)"
echo "  audit $([ -x "$AUDIT_CLI" ] && echo recorded || echo '(kconfig-audit.py missing)')"
echo
echo "VERIFY AFTER BUILD - rc=0 proves nothing, check the artifact:"
echo "  grep -n $key $CFG"
if [ "$val" = "y" ]; then
  echo "  strings vmlinux | grep -c '<a marker string unique to that driver>'   # >=1 means built in"
fi
echo "  md5sum $KDIR/arch/arm64/boot/Image   # must DIFFER from the previous build"
[ "$before_gold" = "$(md5sum "$GOLD" | cut -d' ' -f1)" ] && \
  echo "WARNING: gold did not change - the symbol may already have had that value" >&2
exit 0
