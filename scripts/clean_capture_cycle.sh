#!/bin/bash
# clean_capture_cycle.sh — single capture, power cycle, watch boot.
set -u
DEV=/dev/opiz3w-serial
LOG=/home/host/pvrgl-work/sercap_clean.log

sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1
sleep 1
sudo stty -F $DEV 115200 raw -echo
(sudo setsid bash -c "exec cat $DEV >> $LOG" >/dev/null 2>&1 &)
sleep 1
python3 /home/host/smartplug.py reboot >/dev/null 2>&1
echo "cycled; watching 75s..."
sleep 75
tail -c 3000 $LOG | grep -a . | tail -25
echo "---SSH---"
ssh -o ConnectTimeout=8 orangepi@192.168.0.151 'uptime; uname -r' 2>&1 | head -2
