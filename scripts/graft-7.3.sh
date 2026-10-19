#!/bin/bash
# graft-7.3.sh — graft allwinner-bsp (AIC8800 + sunxi-ng + DTS + dt-bindings) onto v7.3-rc2 KDIR
# Idempotent. Run as host. No power/serial side effects.
set -euo pipefail

SRC=/home/host/kernel-trees/host-build/mainline-7.2
DST=/home/host/kernel-trees/host-build/mainline-7.3
BSP=/home/host/kernel-trees/allwinner-bsp

echo "=== [1/6] verify 7.3-rc2 checked out ==="
if ! grep -q '^PATCHLEVEL = 3' "$DST/Makefile"; then
  echo "ABORT: 7.3 tree not at PATCHLEVEL=3 (still 7.2.4, fetch pending?)"
  exit 1
fi
grep -E '^VERSION|^PATCHLEVEL|^SUBLEVEL' "$DST/Makefile"
git -C "$DST" log --oneline -1

echo "=== [2/6] copy untracked graft files (DTS + dt-bindings headers) ==="
# Only copy paths under arch/ or include/ from 7.2's untracked set (excludes bsp symlink + git noise)
cd "$SRC"
COUNT=0
while read -r f; do
  case "$f" in
    arch/*|include/*) ;;
    *) continue ;;
  esac
  mkdir -p "$DST/$(dirname "$f")"
  cp -a "$SRC/$f" "$DST/$f"
  COUNT=$((COUNT+1))
done < <(git status --porcelain 2>/dev/null | grep '^??' | awk '{print $2}')
echo "copied $COUNT files"

echo "=== [3/6] bsp symlink ==="
ln -sfn "$BSP" "$DST/bsp"
ls -la "$DST/bsp"

echo "=== [4/6] Kconfig glue: source bsp/Kconfig ==="
if ! grep -q 'source "bsp/Kconfig"' "$DST/Kconfig"; then
  # insert after the first 'source "init/Kconfig"' line
  python3 - <<'PY'
import re
p="/home/host/kernel-trees/host-build/mainline-7.3/Kconfig"
s=open(p).read()
anchor='source "init/Kconfig"\n'
if 'source "bsp/Kconfig"' not in s:
    s=s.replace(anchor, anchor+'source "bsp/Kconfig"\n\n', 1)
    open(p,"w").write(s)
    print("Kconfig: inserted bsp/Kconfig")
else:
    print("Kconfig: already present")
PY
else
  echo "Kconfig: already present"
fi

echo "=== [5/6] Makefile glue (LINUXINCLUDE + drivers-y + headers_install) ==="
python3 - <<'PY'
p="/home/host/kernel-trees/host-build/mainline-7.3/Makefile"
s=open(p).read()
changed=[]
# 5a: LINUXINCLUDE bsp/include
if ' -I$(srctree)/bsp/include \\\n' not in s and '-I$(srctree)/bsp/include' not in s:
    a='\t\t-I$(objtree)/include \\\n\t\t$(USERINCLUDE)\n'
    b='\t\t-I$(objtree)/include \\\n\t\t-I$(srctree)/bsp/include \\\n\t\t$(USERINCLUDE)\n'
    if a in s:
        s=s.replace(a,b,1); changed.append("LINUXINCLUDE")
    else:
        print("  WARN: LINUXINCLUDE anchor not found (7.3 drift)")
# 5b: drivers-y += bsp/
if 'drivers-y\t+= bsp/\n' not in s and 'drivers-y += bsp/' not in s:
    a='core-y\t\t:=\ndrivers-y\t:=\n'
    b='core-y\t\t:=\ndrivers-y\t:=\ndrivers-y\t+= bsp/\n'
    if a in s:
        s=s.replace(a,b,1); changed.append("drivers-y")
    else:
        print("  WARN: drivers-y anchor not found")
# 5c: headers_install bsp glue
if 'Makefile.headersinst' not in s.replace('bsp/scripts/Makefile.headersinst',''):
    pass
if 'hdr-inst-bsp' not in s:
    anchor='hdr-inst := -f $(srctree)/scripts/Makefile.headersinst obj\n'
    add=('IS_AOSP = $(shell if [ -d "$(srctree)/android" ] && [ -n "$(KBUILD_EXTMOD)" ]; then echo "y"; fi)\n'
         'ifneq ($(IS_AOSP), y)\n'
         '\thdr-inst-bsp := -f $(srctree)/bsp/scripts/Makefile.headersinst obj\n'
         'else\n'
         '\thdr-inst-bsp := -f $(srctree)/bsp/scripts/Makefile.headersinst dst=$(KBUILD_EXTMOD)/usr/include/bsp obj\n'
         'endif\n')
    if anchor in s:
        s=s.replace(anchor, add+anchor, 1); changed.append("hdr-inst-bsp-def")
    else:
        print("  WARN: hdr-inst anchor not found")
# 5d: headers_install bsp uapi
if 'Makefile.headersinst)=bsp/include/uapi' not in s:
    anchor='\t$(Q)$(MAKE) $(hdr-inst)=arch/$(SRCARCH)/include/uapi\n'
    add='\t$(Q)$(MAKE) $(hdr-inst-bsp)=bsp/include/uapi\n'
    if anchor in s and '$(hdr-inst-bsp)=bsp/include/uapi' not in s:
        s=s.replace(anchor, anchor+add, 1); changed.append("hdr-inst-bsp-uapi")
    else:
        print("  WARN: hdr-inst uapi anchor not found or present")
open(p,"w").write(s)
print("Makefile changes:", changed if changed else "none (already grafted?)")
PY

echo "=== [6/6] DTS Makefile: add sun60i-a733 dtb targets ==="
python3 - <<'PY'
p="/home/host/kernel-trees/host-build/mainline-7.3/arch/arm64/boot/dts/allwinner/Makefile"
s=open(p).read()
if 'sun60i-a733-orangepi-zero3w.dtb' in s:
    print("DTS Makefile: already present")
else:
    # append after last sun55i line or at end
    add='dtb-$(CONFIG_ARCH_SUNXI) += sun60i-a733-cubie-a7a.dtb\ndtb-$(CONFIG_ARCH_SUNXI) += sun60i-a733-cubie-a7s.dtb\ndtb-$(CONFIG_ARCH_SUNXI) += sun60i-a733-cubie-a7z.dtb\ndtb-$(CONFIG_ARCH_SUNXI) += sun60i-a733-orangepi-zero3w.dtb\n'
    if not s.endswith('\n'):
        s+='\n'
    s=s+add
    open(p,"w").write(s)
    print("DTS Makefile: added 4 dtb targets")
PY

echo "=== DONE. verify ==="
grep -n 'bsp/Kconfig' "$DST/Kconfig"
grep -n 'bsp/' "$DST/Makefile" | head -5
grep -n 'sun60i-a733' "$DST/arch/arm64/boot/dts/allwinner/Makefile"
ls "$DST/arch/arm64/boot/dts/allwinner/sun60i-a733-orangepi-zero3w.dts"
