#!/bin/bash
cd /home/host/opikernel/pvrgl-work || exit 1
echo "=== boot-evidence logs (newest first) ==="
ls -alrt --time-style=+'%m-%d %H:%M' sercap_manual_earlycon.log sercap_room_live.log sercap_bootscr_fix_boot.log sercap*.log 2>/dev/null | tail -12
echo
echo "=== now ==="
date '+%m-%d %H:%M:%S'
echo
echo "=== last 12 meaningful lines of the AUTHORITATIVE log ==="
strings sercap_manual_earlycon.log 2>/dev/null | grep -v '^$' | tail -12
echo
echo "=== gate markers present in it? ==="
for m in 'Linux version' 'Unable to handle' 'Waiting for root device' 'Kernel panic' 'Number of UART'; do
  printf '%-28s %s\n' "$m" "$(grep -c "$m" sercap_manual_earlycon.log 2>/dev/null)"
done
