#!/bin/bash
# PA: per-boot card identity (capacity) + partition table + root= per boot block
cd /home/host/opikernel/pvrgl-work || exit 1
L=sercap_room_live.log
echo "== card capacity per U-Boot init (MB) — chronological =="
strings "$L" | grep -nE '^\[' -A0 >/dev/null 2>&1
strings "$L" | grep -E '\[mmc\]: [0-9]+ MB|MB$' | grep -nE 'MB' | head -40
echo
echo "== capacity lines only =="
strings "$L" | grep -oE '\[mmc\]: [0-9]+ MB' | uniq -c
echo
echo "== partition table dumps (U-Boot part list mmc 0) =="
strings "$L" | grep -A8 'Partition Map for MMC device 0' | tail -60
echo
echo "== root= per boot block =="
strings "$L" | grep -oE 'root=PARTUUID=[0-9a-f-]+' | uniq -c
