#!/bin/bash
# PA: what did MMC actually say in the newest capture?
cd /home/host/opikernel/pvrgl-work || exit 1
L=sercap_room_live.log
echo "== last line numbers: Starting kernel vs pinctrl vs mmc =="
strings "$L" | grep -n -E 'Starting kernel|sunxi:pin|mmc0|mmcblk|Waiting for root' | tail -30
echo "== EVERY mmc0 line in the newest block (last 700 lines) =="
strings "$L" | tail -700 | grep -iE 'mmc|sdhci|sdio|card|vmmc|regulator' | tail -40
echo "== mmc0 distinct lines, whole log =="
strings "$L" | grep -o 'mmc0[^]]*' | sed 's/[0-9]\{3,\}/N/g' | sort | uniq -c | sort -rn | head -20
