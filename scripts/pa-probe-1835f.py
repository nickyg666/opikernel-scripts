#!/usr/bin/env python3
"""PA probe #6: mention-queue enqueue path — how a.target/queueId is attached (region 10705600..10709000)."""
BUNDLE = "/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js"
data = open(BUNDLE, 'rb').read()
print(data[10705600:10709000].decode('utf-8', 'replace'))
