#!/bin/bash
# TelegramRunner lane: canonical queue integrity assert (agentic-pool/BACKLOG.md)
cd /home/host/opikernel || exit 1
B=agentic-pool/BACKLOG.md
ls -l --time-style=+%m-%d_%H:%M:%S "$B"
md5sum "$B"
printf 'headings=%s status=%s claimedby=%s fused=%s\n' \
  "$(grep -c '^### BL-' "$B")" \
  "$(grep -c '^status:' "$B")" \
  "$(grep -c '^claimed-by:' "$B")" \
  "$(grep -c '^### ###' "$B")"
echo "--- status histogram ---"
grep '^status:' "$B" | sort | uniq -c
echo "--- BL ids ---"
grep -c '^### BL-' "$B"
