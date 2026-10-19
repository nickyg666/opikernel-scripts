#!/usr/bin/env bash
set -u
echo "== where does the literal 'Failed to determine role for room' live? =="
grep -rln "Failed to determine role for room" /home/host/.hermes/bin/ /home/host/.hermes-web-ui/ /home/host/opikernel/scripts/ /home/host/hermes-agent 2>/dev/null | grep -v '\.bak' | head -20
echo
echo "== 'could not determine role from environment' =="
grep -rln "could not determine role from environment" /home/host/.hermes/bin/ /home/host/.hermes-web-ui/ /home/host/opikernel/scripts/ /home/host/hermes-agent 2>/dev/null | grep -v '\.bak' | head -20
echo
echo "== yolo wrapper =="
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/.hermes/bin/yolo 2>/dev/null
file /home/host/.hermes/bin/yolo 2>/dev/null
