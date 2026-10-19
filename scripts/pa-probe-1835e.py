#!/usr/bin/env python3
"""PA probe #5: dump the real dispatcher (dispatchPendingHandoffs) that consumes queued items."""
BUNDLE = "/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js"
data = open(BUNDLE, 'rb').read()
start = 10982400
print(data[start:start+7000].decode('utf-8', 'replace'))
