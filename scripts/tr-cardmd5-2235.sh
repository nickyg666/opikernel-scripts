#!/bin/bash
# TR bounded action 22:35 — md5 of card mainline artifacts (the deploy verification).
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 tab@192.168.0.149"
$SSH "echo 1 | sudo -S md5sum /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb 2>/dev/null; echo '--- dtb files ---'; echo 1 | sudo -S ls -l --time-style=+%m-%d_%H:%M:%S /mnt/sd/boot/mainline/ | grep -E 'dtb|boot.scr'; echo '--- boot.scr ---'; echo 1 | sudo -S ls -l --time-style=+%m-%d_%H:%M:%S /mnt/sd/boot/boot.scr"
