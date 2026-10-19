#!/usr/bin/env python3
"""PA probe #4: who consumes listQueuedExecutionItems, and is there a concurrency cap / connected gate?"""
import re, hashlib
BUNDLE = "/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js"
data = open(BUNDLE, 'rb').read()
print("md5", hashlib.md5(data).hexdigest(), len(data))

def offs(tok):
    return [m.start() for m in re.finditer(re.escape(tok.encode()), data)]

for tok in ('listQueuedExecutionItems', '_executionQueueBroadcaster', '.connected', 'maxConcurrent',
            'position', 'activeRun', 'runningCount', 'isAgentRunning'):
    o = offs(tok)
    print(tok, len(o), o[:10])

for site in offs('listQueuedExecutionItems'):
    print(f"\n---- call site @{site} ----")
    print(data[max(0, site-1500):site+900].decode('utf-8', 'replace'))
