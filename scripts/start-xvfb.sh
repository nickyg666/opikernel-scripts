#!/bin/bash
# Headed Chromium for bot-resistant research, per Nick 2026-10-03.
# The browser_use tool launches headless (chromium_headless_shell), which is what
# gets us DuckDuckGo CAPTCHAs. A full chromium under Xvfb is present in the
# playwright cache, so run that headed on :99 instead.
export DISPLAY=:99
if pgrep -x Xvfb >/dev/null; then
  echo "Xvfb already running on :99"
else
  nohup Xvfb :99 -screen 0 1920x1080x24 >/tmp/xvfb.log 2>&1 &
  sleep 4
fi
pgrep -a Xvfb | head -2
CHROME=/home/host/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome
[ -x "$CHROME" ] && echo "headed chromium: $CHROME" || echo "MISSING $CHROME"
echo "DISPLAY=$DISPLAY"
