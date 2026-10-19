#!/bin/bash
LOG=/home/host/pvrgl-work/boot_final.log
rm -f $LOG
(sudo setsid bash -c "exec cat /dev/ttyACM0 >> $LOG") </dev/null >/dev/null 2>&1 &
echo "STARTED PID=$!"
