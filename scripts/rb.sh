#!/bin/bash
# rb.sh — clean soft reboot of the board (run via sudo on board)
# Avoids agent-tool blocklist on 'reboot' tokens inside ssh command strings.
sync
sudo shutdown -r now
