#!/bin/bash
# recovery_0830_known_good.sh — boot using card-boot-20260830 PROVEN artifacts
#
# Proven: 2026-08-30 from LIVE board, UHS fix + aic8800 blacklisted.
#   Image beac4ac34c7caf1b11f1220f1ec63964  (6.18.19+ no aic8800 built-in)
#   DTB   d826912215e5c4b4a07932a617d483b5  (UHS-stripped sdmmc@4021000)
#   tiny-uInitrd 06e5e6c6b1d2ec6c9e05c4711a5f1719 (1.5MB)
#   boot.scr bace60480887f41a3368779f240c7cf7  (tries mainline → vendor fallback)
#   orangepiEnv.txt: module_blacklist=aic8800_btlpm + swiotlb=65536
#
# Pre-reqs:
#   - card-boot-20260830.tar.gz in /home/host/opikernel/backups/
#   - Board SD physically in tab (.149) reader if we need to reflash
#   - /dev/ttyACM0 is the picoprobe (115200, sudo)
#
# This script:
#   1. Power-cycles board (smartplug opiz3w)
#   2. Resets CDC-ACM (modprobe -r cdc_acm && modprobe cdc_acm)
#   3. Intercepts U-Boot (break + send Enter)
#   4. Loads beac4ac3 Image at 0x41000000, d8269122 DTB at 0x43000000
#   5. booti 0x41000000 - 0x43000000 (raw mainline, NO initrd — tiny-uInitrd is uImage format wrong for booti)
#   6. Or bootm 0x41000000 - 0x43000000 (vendor uImage path)
#
# Use this when board .138/.151 is alive at U-Boot but kernel panics.
set -e

PROBE="/dev/ttyACM0"
LOG="/home/host/opikernel/pvrgl-work/recovery_0830.log"
KNOWN="/home/host/opikernel/backups/card-boot-20260830"
IMAGE="beac4ac34c7caf1b11f1220f1ec63964"   # 6.18.19+, NO aic8800 built-in
DTB="d826912215e5c4b4a07932a617d483b5"       # UHS-stripped, de-iommu safe
TINY="06e5e6c6b1d2ec6c9e05c4711a5f1719"      # 1.5MB, full ext4+USB modules
BOOTSCR="bace60480887f41a3368779f240c7cf7"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# 1) Kill any stale serial holders
log "Kill stale serial readers"
for p in $(sudo lsof -t "$PROBE" 2>/dev/null); do
  sudo kill -9 "$p" 2>/dev/null || true
done
pkill -9 -f 'boot_clean' 2>/dev/null || true
pkill -9 -f 'boot_mainline' 2>/dev/null || true
pkill -9 -f 'boot_v' 2>/dev/null || true
pkill -9 -f 'sercap' 2>/dev/null || true
sleep 1

# 2) Verify known-good artifacts
log "Verify known-good artifacts"
ls -la "$KNOWN/Image" "$KNOWN/sun60i-a733-orangepi-zero3w.dtb" "$KNOWN/tiny-uInitrd" "$KNOWN/boot.scr" 2>&1 | tee -a "$LOG"
ACT_IMG=$(md5sum "$KNOWN/Image" | awk '{print $1}')
ACT_DTB=$(md5sum "$KNOWN/sun60i-a733-orangepi-zero3w.dtb" | awk '{print $1}')
ACT_TINY=$(md5sum "$KNOWN/tiny-uInitrd" | awk '{print $1}')
log "  Image md5: $ACT_IMG (expected $IMAGE)"
log "  DTB   md5: $ACT_DTB (expected $DTB)"
log "  tiny  md5: $ACT_TINY (expected $TINY)"
if [ "$ACT_IMG" != "$IMAGE" ] || [ "$ACT_DTB" != "$DTB" ]; then
  log "ERROR: artifacts don't match expected. Refusing to flash."
  exit 1
fi

# 3) Power cycle
log "Power cycle (smartplug opiz3w)"
python3 /home/host/smartplug.py off || true
sleep 8
python3 /home/host/smartplug.py on  || true
sleep 4

# 4) Reset CDC-ACM (REQUIRED after power cycle)
log "CDC-ACM reset (modprobe -r && modprobe)"
sudo modprobe -r cdc_acm 2>&1 | tee -a "$LOG"
sleep 2
sudo modprobe cdc_acm 2>&1 | tee -a "$LOG"
sleep 3

# 5) Open port
log "Open $PROBE"
sudo chmod 666 "$PROBE"
exec 3<>"$PROBE"
# Configure raw 115200 8N1
stty -F "$PROBE" 115200 cs8 -cstopb -parenb -ixon -ixoff -crtscts \
    -icanon -echo -echoe -echok -echoctl -echoke -isig -iexten \
    -noflsh min 0 time 0 <&3 || true
sleep 1

# 6) Background reader
READER_LOG="/home/host/opikernel/pvrgl-work/recovery_0830_reader.log"
: > "$READER_LOG"
( while true; do
    if read -t 0.5 -r -u 3 -n 4096 byte; then
      printf '%s' "$byte" >> "$READER_LOG"
    fi
  done ) &
RPID=$!
log "Reader PID=$RPID"

# 7) Break to U-Boot (need to send during ~4800ms window)
log "Spam CR to catch U-Boot (12s window)"
END=$(($(date +%s) + 12))
COUNT=0
while [ $(date +%s) -lt $END ]; do
  printf '\r' >&3
  sleep 0.05
  COUNT=$((COUNT+1))
done
log "  sent $COUNT CR"

# 8) Send boot sequence — try mainline with the clean image
#    Note: kernel already on SD. We're loading from SD via ext4load.
log "Load mainline Image beac4ac3 → 0x41000000"
printf 'ext4load mmc 0:1 0x41000000 /boot/mainline/Image\r' >&3
sleep 25

log "Load mainline DTB d8269122 → 0x43000000"
printf 'ext4load mmc 0:1 0x43000000 /boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015\r' >&3
sleep 6

# 9) fdt setup for bootargs
log "fdt addr/resize"
printf 'fdt addr 0x43000000\r' >&3; sleep 1
printf 'fdt resize 65536\r' >&3; sleep 1

# 10) Set bootargs (no aic8800 blacklist needed — kernel has no aic8800 built-in)
log "setenv bootargs"
printf 'setenv bootargs root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 console=ttyS0,115200 loglevel=7 earlyprintk=sunxi-uart,0x02500000 swiotlb=65536 module_blacklist=aic8800_btlpm,aic8800_fdrv ipv6.disable=1\r' >&3
sleep 2

# 11) booti (raw Image)
log "booti 0x41000000 - 0x43000000"
printf 'booti 0x41000000 - 0x43000000\r' >&3
sleep 3

# 12) Wait for SSH
log "Wait 90s for kernel boot + SSH"
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18; do
  sleep 5
  for ip in 192.168.0.151 192.168.0.138; do
    if timeout 2 sshpass -p orangepi ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
       orangepi@"$ip" 'echo OK' 2>/dev/null | grep -q OK; then
      log "SSH OK at $ip"
      kill $RPID 2>/dev/null || true
      exit 0
    fi
  done
  log "  T+${i}*5s: not yet"
done

log "SSH never came up. Reader log tail:"
tail -50 "$READER_LOG" | strings | tail -20
kill $RPID 2>/dev/null || true
exit 1
