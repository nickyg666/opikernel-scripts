#!/usr/bin/env bash
# audit-kver-prefix.sh — WHOLE-TREE module-release audit.
#
# WHY THIS EXISTS (2026-09-30, kernel-architect):
# modprobe resolves a module by `uname -r`, so the ONLY dir the kernel can ever
# read is lib/modules/$(uname -r). Every other dir is invisible until the day
# uname changes. The 465G card carried 16 release dirs; 9 of them held .ko whose
# own vermagic did not match the dir they sat in, and a SECOND
# 7.3.0-rc2-00018-g<othercommit>-dirty dir sorted adjacent to the live one.
# A gate that only inspects the live dir passes while the card is one uname
# rename away from loading a 17-day-old module.
#
# Two independent failures, two checks:
#   DIR_VERMAGIC_MISMATCH  a .ko under dir D carries a vermagic != D
#                          (the file the kernel would load is not the file
#                          anyone audited; `ls *.ko | wc -l` cannot see it)
#   PREFIX_SIBLING         a dir != live release shares the live release's
#                          release-number token, e.g. 7.3.0-rc2-00018-*
#                          (any glob/prefix path silently mixes two commits)
#
# The two are not the same: a clean-relative dir can still be a prefix sibling
# of the live one, and a mismatched dir can be in a totally different series.
# Both must be zero.
#
# READ-ONLY by construction: reads dir names and `modinfo -F vermagic`. Never
# writes, never mounts, never depmods. Card identity is the caller's job.
#
# USAGE:
#   audit-kver-prefix.sh /path/to/lib/modules                 # local tree
#   LIVE=<release> audit-kver-prefix.sh -                      # stdin/remote
# Exit 0 clean, 1 findings (each on its own line, prefixed), 2 usage error.
set -uo pipefail

MODROOT=${1:-}
[ -n "$MODROOT" ] || { echo "usage: $0 <lib/modules dir>"; exit 2; }
[ -d "$MODROOT" ] || { echo "NO_MODROOT $MODROOT"; exit 2; }

# The live release: whatever the caller proved from the booted Image banner.
# Never guessed from a dir name — that is the whole bug.
LIVE=${LIVE:-}
if [ -z "$LIVE" ]; then
  echo "NO_LIVE no LIVE=<uname -r> given; refusing to guess the release from a dir name"
  exit 2
fi

fail=0
note() { printf '%s\n' "$*"; }
bad()  { printf ' ! %s\n' "$*"; fail=1; }

# Release-number token: 7.3.0-rc2-00018-gdeadbeef-dirty -> 7.3.0-rc2-00018
# git describe's `-NNNNN-g<sha>` counter is the only part that distinguishes
# two builds of the SAME base release, and it is what a `*-NNNNN-*` glob keys
# on. So it is the collision unit. A release with no counter (7.3.0-rc2-dirty)
# is its own token and has no siblings.
tok() { printf '%s' "$1" | sed -n 's/^\(.*-[0-9][0-9]*\)-g[0-9a-f]\{4,\}.*$/\1/p'; }
LIVE_TOK=$(tok "$LIVE")
[ -n "$LIVE_TOK" ] || { echo "NO_LIVE_TOKEN cannot derive a release-number token from '$LIVE'"; exit 2; }

note "MODROOT=$MODROOT"
note "LIVE=$LIVE  token=$LIVE_TOK"
note "== every release dir =="
for d in "$MODROOT"/*/; do
  [ -d "$d" ] || continue
  b=$(basename "$d")
  case "$b" in
    .*) continue ;;                 # .quarantine-* is intentional and inert
  esac
  n=$(find "$d" -name '*.ko' 2>/dev/null | wc -l)
  bad_vm=0; bad_list=""
  for f in $(find "$d" -name '*.ko' 2>/dev/null); do
    vm=$(modinfo -F vermagic "$f" 2>/dev/null | cut -d' ' -f1)
    if [ "$vm" != "$b" ]; then
      bad_vm=$((bad_vm+1))
      bad_list="$bad_list $(basename "$f")@${vm:-NONE}"
    fi
  done
  mark=ok
  [ "$bad_vm" -gt 0 ] && mark=MISMATCHED
  printf '  %-52s ko=%-4s %s\n' "$b" "$n" "$mark"
  if [ "$bad_vm" -gt 0 ]; then
    bad "DIR_VERMAGIC_MISMATCH $b: $bad_vm .ko do not carry this dir's name ->$bad_list"
  fi
done

note "== prefix siblings of the live release =="
sib=0
for d in "$MODROOT"/*/; do
  [ -d "$d" ] || continue
  b=$(basename "$d")
  case "$b" in .*) continue ;; esac
  [ "$b" = "$LIVE" ] && continue
  t=$(tok "$b")
  if [ -n "$t" ] && [ "$t" = "$LIVE_TOK" ]; then
    sib=$((sib+1))
    bad "PREFIX_SIBLING $b shares release token $LIVE_TOK with the live dir $LIVE (any $LIVE_TOK-* glob mixes two commits)"
  fi
done
[ "$sib" -eq 0 ] && note "  none"

note "== live dir itself =="
if [ ! -d "$MODROOT/$LIVE" ]; then
  bad "RELEASE_MISSING no $MODROOT/$LIVE (modprobe would find nothing for uname -r=$LIVE)"
else
  n=$(find "$MODROOT/$LIVE" -name '*.ko' 2>/dev/null | wc -l)
  note "  .ko=$n"
  [ "$n" -gt 0 ] || bad "KO_NONE $MODROOT/$LIVE holds no .ko"
  for idx in modules.dep modules.builtin; do
    [ -f "$MODROOT/$LIVE/$idx" ] && note "  $idx present ($(stat -c %s "$MODROOT/$LIVE/$idx") B)" \
                               || note "  $idx ABSENT (modprobe resolves builtin-only names as not-found)"
  done
fi

echo
if [ "$fail" = 1 ]; then echo "KVER_PREFIX_FAIL"; exit 1; fi
echo "KVER_PREFIX_CLEAN live=$LIVE token=$LIVE_TOK"
