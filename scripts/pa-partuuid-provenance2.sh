#!/bin/bash
# PA: provenance of PARTUUIDs — ripgrep, bounded
cd /home/host/opikernel || exit 1
echo "== 486ea4ae (boot.scr root=) =="
timeout 60 rg -l --no-messages -g '!builds/**' -g '!*.log' -g '!*.pdf' 486ea4ae . 2>/dev/null | head -12
echo "== 442af407 (AGENTS canon root=) =="
timeout 60 rg -l --no-messages -g '!builds/**' -g '!*.log' -g '!*.pdf' 442af407 . 2>/dev/null | head -12
echo "== bootargs strings in stage/scripts =="
timeout 60 rg -n --no-messages -g '!builds/**' -g '!*.log' 'PARTUUID=[0-9a-f]{8}' scripts stage kernel 2>/dev/null | head -20
echo "== dts source trees =="
timeout 60 rg --files -g 'sun60iw2*.dtsi' /home/host 2>/dev/null | head -8
