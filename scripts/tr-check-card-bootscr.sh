#!/bin/bash
# tr-check-card-bootscr.sh — pull + inspect the card's boot.scr (silent-death vector)
cd /home/host/opikernel
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 tab@192.168.0.149"
mkdir -p pvrgl-work/card-inspect
timeout 40 $SSH "cat /mnt/sd/boot/boot.scr" 2>/dev/null > pvrgl-work/card-inspect/boot.scr
ls -l --time-style=+%m-%d_%H:%M:%S pvrgl-work/card-inspect/boot.scr
echo "=== magic (expect 27051956 uImage script) ==="
head -c4 pvrgl-work/card-inspect/boot.scr | xxd -p
echo "=== strings ==="
strings -n 3 pvrgl-work/card-inspect/boot.scr
