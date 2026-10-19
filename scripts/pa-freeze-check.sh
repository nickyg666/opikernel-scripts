#!/bin/bash
# PA: post-swap state freeze check
cd /home/host/opikernel/pvrgl-work || exit 1
L=sercap_room_live.log
date '+now=%m-%d %H:%M:%S'
md5sum "$L"
ls -l --time-style=+%m-%d_%H:%M:%S "$L"; sleep 10; ls -l --time-style=+%m-%d_%H:%M:%S "$L"
echo "== holder =="; fuser /dev/opiz3w-serial 2>&1
echo "== plug =="; cd /home/host && timeout 60 python3 -c "import smartplug as sp; print('is_on=', [p for p in sp._client().plugs.list() if p.nickname=='opiz3w'][0].is_on)"
echo "== board reachable? =="; timeout 5 ping -c1 -W2 192.168.0.151 >/dev/null 2>&1 && echo PING_OK || echo PING_FAIL
echo "== newest boot verdict line count since last pinctrl =="; cd /home/host/opikernel/pvrgl-work && strings $L | tail -3
