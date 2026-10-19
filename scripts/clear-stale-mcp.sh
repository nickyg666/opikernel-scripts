#!/usr/bin/env python3
"""Drop ONLY the stale ekko-studio-plan entry from the MCP schema cache.

Context (2026-10-02, Nick's request): the live ~/.hermes/config.yaml still has
five studio servers (hermes-studio, ekko-studio-api, ekko-studio-browser,
ekko-studio-devices, ekko-studio-use). Only ekko-studio-plan was removed on
2026-09-26 (see config.yaml.bak-ekkoplan-20260926-021815). The schema cache was
never invalidated, so the prompt generator kept emitting a
<studio_task_plan_context> block for a server that does not exist.

Rather than deleting the whole cache (it would be regenerated, but there is no
reason to discard the other five servers' valid entries), back it up and drop
just the phantom key.
"""
import json
import os
import shutil
import sys
import time

CACHE = os.path.expanduser('~/.hermes/cache/mcp_schema_cache.json')
PHANTOM = 'ekko-studio-plan'

if not os.path.exists(CACHE):
    sys.exit('no cache at %s' % CACHE)

bak = '%s.bak-%s' % (CACHE, time.strftime('%Y%m%d-%H%M%S'))
shutil.copy2(CACHE, bak)

with open(CACHE) as fh:
    data = json.load(fh)

before = list(data.keys())
if PHANTOM not in data:
    print('nothing to do - %s already absent' % PHANTOM)
    print('cache keys: %s' % ', '.join(before))
    sys.exit(0)

removed = data.pop(PHANTOM)

# Write atomically so a crash cannot leave a truncated cache.
tmp = CACHE + '.new'
with open(tmp, 'w') as fh:
    json.dump(data, fh, indent=2, sort_keys=True)
os.replace(tmp, CACHE)

print('removed %s (%d entries)' % (PHANTOM, len(removed)))
print('backup: %s' % bak)
print('keys now: %s' % ', '.join(sorted(data.keys())))
