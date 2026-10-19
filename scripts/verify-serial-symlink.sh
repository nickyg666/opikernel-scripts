#!/bin/bash
# verify-serial-symlink.sh — prove the propagation actually took, from the live host.
cd /home/host/opikernel || exit 1

echo "=== 1. device identity ==="
ls -l /dev/opiz3w-serial /dev/ttyACM0 /dev/ttyACM1
python3 - <<'PY'
import os
a, b, c = (os.stat(p).st_rdev for p in ("/dev/opiz3w-serial", "/dev/ttyACM0", "/dev/ttyACM1"))
print("all three paths are the SAME device:", a == b == c, "rdev=", a)
PY

echo
echo "=== 2. rewritten live set now points at the symlink ==="
for f in pvrgl-work/pipeline6_earlycon.py pvrgl-work/manual_boot_earlycon.py \
         pvrgl-work/pipeline8_bootscr.py pvrgl-work/boot_and_capture.sh \
         scripts/serial_capture.py scripts/clean_capture_cycle.sh \
         scripts/claim-serial-port.sh; do
  printf '%-42s symlink=%s  literal-left=%s\n' "$f" \
    "$(grep -c 'opiz3w-serial' "$f")" \
    "$(grep -c '/dev/ttyACM0' "$f")"
done

echo
echo "=== 3. reconciler idempotency (run twice, expect no-op second time) ==="
sudo /usr/local/bin/opiz3w-serial-compat.sh
sudo /usr/local/bin/opiz3w-serial-compat.sh

echo
echo "=== 4. --ensure is still a no-op while the single owner holds the port ==="
python3 pvrgl-work/serial_single_owner.py --ensure && echo "--ensure rc=0"
echo "owner pid file: $(cat pvrgl-work/.serial_owner.pid 2>/dev/null)"

echo
echo "=== 5. exactly one holder on the real node ==="
sudo fuser -v /dev/ttyACM1 2>&1 || true

echo
echo "=== 6. capture is live (log mtime + tail) ==="
stat -c '%n  size=%s  mtime=%y' pvrgl-work/sercap_room_live.log
tail -c 400 pvrgl-work/sercap_room_live.log

echo
echo "=== 7. cron log (should be silent when nothing to do) ==="
tail -5 pvrgl-work/serial_owner_cron.log 2>&1
