#!/bin/bash
# TR bounded action 22:36 — close the boot.scr residual: decode the card's boot.scr and
# verify its cp.b copy-length matches the FIXED Image size (41666568 = 0x27C0008).
set -e
W=/tmp/tr-bootscr; mkdir -p $W
sshpass -p 1 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 tab@192.168.0.149 \
  "echo 1 | sudo -S cat /mnt/sd/boot/boot.scr" > $W/boot.scr 2>/dev/null
echo "== FETCHED =="; ls -l --time-style=+%m-%d_%H:%M:%S $W/boot.scr; md5sum $W/boot.scr /home/host/opikernel/stage/7.3-stage/boot/boot.scr 2>/dev/null || true
echo "== IMAGE PAYLOAD =="
mkimage -l $W/boot.scr 2>&1 | head -20
echo "== EMBEDDED SCRIPT =="
dd if=$W/boot.scr bs=1 skip=64 2>/dev/null | tr -d '\377' | strings | head -60
echo "== SIZES =="
printf 'fixed Image  = %s (0x%X)\n' "$(stat -c%s /home/host/opikernel/stage/7.3-stage/boot/mainline/Image)" "$(stat -c%s /home/host/opikernel/stage/7.3-stage/boot/mainline/Image)"
