#!/bin/bash
# Apply the staged webhook-platform block to the live gateway config, then restart the gateway.
# Rollback on any failure. Run as: bash scripts/apply-webhook-platform.sh
set -u
CFG=/home/host/.hermes/config.yaml
CAND=/home/host/opikernel/pvrgl-work/config.yaml.pa-webhook-candidate
BAK=/home/host/.hermes/config.yaml.bak-pre-webhook-$(date +%Y%m%d-%H%M%S)

cp -a "$CFG" "$BAK" || exit 1
echo "backup: $BAK $(md5sum < "$BAK")"

# Only proceed when the change is the known 7-line append.
if ! diff <(cat "$CFG") "$CAND" | grep -q '^1471a1472,1478$'; then
  echo "REFUSED: candidate is not the known 7-line addition; aborting"; exit 2
fi

cp -a "$CAND" "$CFG" || exit 3
if ! /home/host/.hermes/hermes-agent/venv/bin/python -c "
import yaml,sys
c=yaml.safe_load(open('$CFG'))
assert 'platforms' in c and 'webhook' in c['platforms'], 'no webhook platform'
wh=c['platforms']['webhook']
print('YAML OK platforms=', list(c['platforms']), 'enabled=', wh.get('enabled'), 'port=', (wh.get('extra') or {}).get('port'))
"; then
  cp -a "$BAK" "$CFG"; echo "ROLLED BACK (yaml invalid)"; exit 4
fi
echo "applied: $(md5sum < "$CFG")"

systemctl --user restart hermes-gateway
sleep 20
systemctl --user is-active hermes-gateway
ss -ltn 2>/dev/null | grep ':8644' || echo "8644 NOT listening"
tail -n 12 /home/host/.hermes/logs/gateway.log
