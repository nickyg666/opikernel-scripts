#!/bin/bash
# TelegramRunner 20260920-2005: does the PUBLISHED artifact carry the wakeupgen port?
# A released Image without the driver reproduces the pinctrl -517 boot failure exactly.
set -u
REPO=/home/host/opikernel-7.3-artifacts
cd "$REPO" || exit 1
for d in 20260920-231110-eff8af11 20260920-143001-3056d664; do
  p="builds/$d/Image.xz"
  [ -f "$p" ] || { echo "$d MISSING $p"; continue; }
  wg=$(xzcat "$p" | strings -a | grep -ci wakeupgen)
  magic=$(xzcat "$p" | head -c4 | xxd -p)
  size=$(xzcat "$p" | wc -c)
  files=$(ls builds/$d | tr '\n' ' ')
  echo "$d wakeupgen_strings=$wg magic=$magic uncompressed=$size"
  echo "   files: $files"
done
echo "--- git HEAD contents for the two dirs ---"
git -C "$REPO" ls-tree -r --name-only HEAD -- builds | grep -E 'eff8af11|3056d664' | sed 's/^/  /'
echo "--- HEAD ---"
git -C "$REPO" log -1 --format='%h %ad %s' --date=iso
