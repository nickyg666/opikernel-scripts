#!/bin/bash
exec 0</dev/null
exec >/dev/null 2>&1
exec cat /dev/ttyACM0 >> /home/host/opikernel/pvrgl-work/sercap_go.log
