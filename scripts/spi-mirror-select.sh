#!/bin/bash
# Mirror the primary display onto the SPI panel.
# - If an external display (HDMI/DP on card0) is connected: mirror the real
#   gdm X session (:0/:2, whichever is live) - NOT the Xvfb dummy.
# - Else (headless): mirror Xvfb :1 (720p dummy) so GPU apps still show.
AUTH=/run/user/1000/gdm/Xauthority
[ -r "$AUTH" ] || AUTH=/run/user/127/gdm/Xauthority

# True if the given display is a real X server (has the root window) and not
# the Xvfb dummy on :1.
is_real_display() {
    local d="$1"
    DISPLAY="$d" XAUTHORITY="$AUTH" xdpyinfo >/dev/null 2>&1 || return 1
    # Xvfb is at :1 - skip it when looking for the real session
    [ "$d" = ":1" ] && return 1
    return 0
}

find_real_display() {
    for d in :0 :2 :3; do
        if is_real_display "$d"; then echo "$d"; return; fi
    done
    echo ""
}

while true; do
    ext=0
    for c in /sys/class/drm/card0-*/status; do
        [ "$(cat "$c" 2>/dev/null)" = "connected" ] && ext=1
    done

    if [ $ext -eq 1 ]; then
        D=$(find_real_display)
        if [ -z "$D" ]; then
            # Session not up yet - wait and retry
            sleep 3
            continue
        fi
        echo "spi-mirror-select: mirroring real display $D (ext=1)"
        DISPLAY="$D" XAUTHORITY="$AUTH" /home/orangepi/spi-mirror "$D"
    else
        echo "spi-mirror-select: mirroring dummy :1 (ext=0)"
        DISPLAY=:1 /home/orangepi/spi-mirror :1
    fi
    echo "spi-mirror-select: spi-mirror exited, restarting (ext=$ext)"
    sleep 3
done
