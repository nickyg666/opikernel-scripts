#!/bin/bash
# room-noise-forensics.sh — why do raw JSON tool results appear as room messages?
echo "=== bridge / gc post paths ==="
ls -l /home/host/bin/gc-say /home/host/opikernel/scripts/gc-post.py 2>&1
echo
echo "=== who can post tool-result-shaped bodies ==="
grep -rln 'workspace_diff\|tool_result\|tool_calls' /home/host/opikernel/scripts/*.py /home/host/bin/* 2>/dev/null | head
echo
echo "=== group-chat bridge process ==="
pgrep -af 'group.chat|bridge' 2>/dev/null | grep -v grep | head -6
echo
echo "=== room noise sample: last 10 room messages, trimmed ==="
/home/host/bin/gc-say --read --limit 10 2>&1 | cut -c1-160 | tail -12
