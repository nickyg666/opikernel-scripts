#!/usr/bin/env python3
"""PA: build a VALIDATED candidate config that restores the top-level
platforms.webhook block (HA -> Hermes :8644) lost from the live config.
Writes ONLY to a staging copy - never touches /home/host/.hermes/config.yaml."""
import re, yaml, sys, json

LIVE = '/home/host/.hermes/config.yaml'
BAK = '/home/host/.hermes/config.yaml.bak-ha-bridge'
OUT = '/home/host/opikernel/pvrgl-work/config.yaml.pa-webhook-candidate'

live = open(LIVE).read()
if re.search(r'^platforms:', live, re.M):
    print('SKIP: live config already has a top-level platforms: key'); sys.exit(0)
if 'webhook' in live:
    print('SKIP: live config already mentions webhook'); sys.exit(0)

bak = open(BAK).read()
m = re.search(r'^platforms:\n(?:[ \t].*\n|\n)*', bak, re.M)
print('bak block found:', bool(m), 'bytes:', len(m.group(0)) if m else 0)
block = m.group(0) if m else (
    'platforms:\n  webhook:\n    enabled: true\n    extra:\n'
    '      host: 127.0.0.1\n      port: 8644\n      secret: "PLACEHOLDER"\n')

cand = live.rstrip('\n') + '\n' + block
open(OUT, 'w').write(cand)

d = yaml.safe_load(open(OUT))
wh = d.get('platforms', {}).get('webhook', {})
print('CANDIDATE YAML-VALID:', OUT)
print('bytes live -> candidate:', len(live), '->', len(cand))
print('platforms keys:', list(d.get('platforms', {}).keys()))
print('webhook enabled:', wh.get('enabled'), 'host:', wh.get('extra', {}).get('host'),
      'port:', wh.get('extra', {}).get('port'),
      'secret_set:', bool(wh.get('extra', {}).get('secret')))
print('live top-level keys unchanged:', d.get('_config_version'), d.get('kanban') is not None)
