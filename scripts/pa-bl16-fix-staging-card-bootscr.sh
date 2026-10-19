#!/bin/bash
# PA — BL-16: put a canonical boot.scr on the staging card (32G, PARTUUID 486ea4ae-01)
# mounted at tab.149:/mnt/sd. Backup first, write, sync, read back md5 FROM THE CARD.
set -u
CANON=/home/host/opikernel-7.3-artifacts/builds/20260920-072325-74090621/boot.scr.card-20260918-verified
STAMP=$(date +%Y%m%d-%H%M%S)
TAB="tab@192.168.0.149"
P=1

echo "== local canonical =="
ls -l "$CANON"; md5sum "$CANON"; head -c4 "$CANON" | od -An -tx1

echo "== push to tab =="
base64 -w0 "$CANON" | sshpass -p "$P" ssh -o StrictHostKeyChecking=no "$TAB" \
  "cat > /tmp/boot.scr.pa-$STAMP.b64 && base64 -d /tmp/boot.scr.pa-$STAMP.b64 > /tmp/boot.scr.pa-$STAMP" || exit 1
sshpass -p "$P" ssh -o StrictHostKeyChecking=no "$TAB" \
  "md5sum /tmp/boot.scr.pa-$STAMP; ls -l /tmp/boot.scr.pa-$STAMP"

echo "== backup card script, then write =="
sshpass -p "$P" ssh -o StrictHostKeyChecking=no "$TAB" \
  "echo $P | sudo -S cp -a /mnt/sd/boot/boot.scr /mnt/sd/boot/boot.scr.pre-PA-$STAMP.bak && \
   echo $P | sudo -S cp /tmp/boot.scr.pa-$STAMP /mnt/sd/boot/boot.scr && \
   echo $P | sudo -S sync && \
   echo '-- after write --' && ls -l /mnt/sd/boot/boot.scr /mnt/sd/boot/boot.scr.pre-PA-$STAMP.bak && \
   md5sum /mnt/sd/boot/boot.scr /mnt/sd/boot/boot.scr.pre-PA-$STAMP.bak"

echo "== read back from card (second, independent read) =="
sshpass -p "$P" ssh -o StrictHostKeyChecking=no "$TAB" "md5sum /mnt/sd/boot/boot.scr; strings /mnt/sd/boot/boot.scr | head -8"
