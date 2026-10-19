#!/bin/bash
# PA: detail on the newest 7.3 capture block
cd /home/host/opikernel/pvrgl-work || exit 1
L=sercap_room_live.log
echo "== SIZE/mtime now =="
ls -l --time-style=+%m-%d_%H:%M:%S "$L"
echo "== boot-block boundaries =="
strings "$L" | grep -n -E 'U-Boot 2018|Linux version|Starting kernel|Model:|Kernel command line|Bootargs' | tail -25
echo "== last boot: everything after the LAST 'Linux version' =="
strings "$L" | awk '/Linux version/{n=NR} {a[NR]=$0} END{for(i=n;i<=NR;i++) print a[i]}' | head -40
echo "== count lines after last Linux version =="
strings "$L" | awk '/Linux version/{n=NR} END{print "lines_after_last_banner="NR-n}' 2>/dev/null
strings "$L" | awk 'BEGIN{c=0} /Linux version/{c=0} {c++} END{print "tail_lines="c}'
echo "== pinctrl / ccu / mmc / sdc mentions in WHOLE log =="
for p in 'sunxi pinctrl version' 'pinctrl' 'sun60iw2_ccu' 'mmc0' 'mmc1' '/soc/mmc' 'sdc0' 'sunxi-mmc' 'dwmmc' 'vqmmc'; do
  printf '%-28s %s\n' "$p" "$(strings "$L" | grep -c "$p")"
done
echo "== distinct Tainted lines =="
strings "$L" | grep -oE 'Tainted: G[^ ]*' | sort | uniq -c | sort -rn | head
echo "== 7.3 banner variants =="
strings "$L" | grep -E 'Linux version [0-9]' | sort | uniq -c
echo "== STARTING KERNEL count (U-Boot handoff) =="
strings "$L" | grep -c 'Starting kernel'
