#!/bin/bash
# Test neato router (OmniRoute) model connectivity for freecode + omni/freeAF
KEY=$(grep -A3 'name: neato' /home/host/.hermes/config.yaml | grep api_key | awk '{print $2}')
echo "=== test 1: model 'freecode' (watchdog nudge model) ==="
timeout 45 curl -s -X POST http://192.168.0.168:20128/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $KEY" \
  -d '{"model":"freecode","messages":[{"role":"user","content":"reply with OK"}],"max_tokens":5}' | head -c 500
echo
echo
echo "=== test 2: model 'omni/freeAF' (room agent model) ==="
timeout 45 curl -s -X POST http://192.168.0.168:20128/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $KEY" \
  -d '{"model":"omni/freeAF","messages":[{"role":"user","content":"reply with OK"}],"max_tokens":5}' | head -c 500
echo
echo
echo "=== hermes-webui gateway procs ==="
ps -eo pid,etime,args | grep -iE "hermes-web-ui|gateway" | grep -v grep | head -8
