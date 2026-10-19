#!/bin/bash
# tr-bounded-bootverdict.sh — TelegramRunner bounded action: verdict on frozen capture + port owner
cd /home/host/opikernel || exit 1
L=pvrgl-work/sercap_room_live.log

echo "=== pid 4967 (port owner) ==="
ps -o pid,etime,cmd -p 4967 2>&1 | tail -2

echo "=== verdict greps in frozen capture ($(wc -c <"$L") B) ==="
for p in "Waiting for root device" "Kernel panic" "login:" "systemd" "pinctrl" "Freeing unused kernel memory" "Run /sbin/init"; do
  n=$(grep -ac "$p" "$L" 2>/dev/null)
  printf '%-34s %s\n' "$p" "$n"
done

echo "=== last 4 raw non-empty lines ==="
tail -c 800 "$L" | tr -d '\r' | grep -a . | tail -4

echo "=== board ping ==="
ping -c1 -W2 192.168.0.151 2>&1 | tail -1
