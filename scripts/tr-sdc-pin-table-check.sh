#!/bin/bash
# TelegramRunner bounded action 17:52 — does the 7.3 pin table carry the SDC pins/functions the booted DTB asks for?
T=/home/host/kernel-trees/host-build/mainline-7.3
D=$T/drivers/pinctrl/sunxi
echo "== trees =="
ls -d /home/host/kernel-trees/*/ 2>/dev/null
echo "== files =="
ls -l --time-style=+%m-%d_%H:%M:%S "$D/pinctrl-sun60iw2.c" "$D/pinctrl-sunxi-bsp.c" 2>&1
echo "== DTB-required pins present in pinctrl-sun60iw2.c =="
for P in PF0 PF1 PF3 PF4 PF5 PC0 PC1 PC5 PC6 PC8 PC9 PC10 PC11 PC13 PC14 PC15 PC16 PG0 PG1 PG2 PG3 PG4 PG5; do
  n=$(grep -c "\"$P\"" "$D/pinctrl-sun60iw2.c" 2>/dev/null)
  printf "%s=%s " "$P" "$n"
done
echo
echo "== DTB-required function names =="
for F in sdc0 sdc1 sdc2; do printf "%s=%s " "$F" "$(grep -c "\"$F\"" "$D/pinctrl-sun60iw2.c" 2>/dev/null)"; done
echo
echo "== sun50i table sizes (npins sanity) =="
grep -n "sun60iw2_pins\[\]\|sun60iw2_pin_function\[\]\|\.npins\|\.npin_functions\|sun60iw2_pinctrl_data" "$D/pinctrl-sun60iw2.c" 2>/dev/null | head -20
