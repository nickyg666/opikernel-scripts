#!/bin/bash
# tr-check-card-bootscr2.sh — retry with stderr visible
cd /home/host/opikernel
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 tab@192.168.0.149"
mkdir -p pvrgl-work/card-inspect
timeout 40 $SSH "ls -l /mnt/sd/boot/; stat -c '%s %n' /mnt/sd/boot/boot.scr; echo 1 | sudo -S cat /mnt/sd/boot/boot.scr > /tmp/bs.scr 2>/dev/null; wc -c /tmp/bs.scr; md5sum /tmp/bs.scr; cat /tmp/bs.scr" > pvrgl-work/card-inspect/out.txt 2>&1
cat pvrgl-work/card-inspect/out.txt | grep -v Warning
echo "=== host-side dump ==="
cd /home/host/opikernel/pvrgl-work/card-inspect && sed -n '/^27051956/,$p' out.txt 2>/dev/null | head -c 600 | xxd | head -8
