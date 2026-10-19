#!/usr/bin/env python3
"""PA probe #7: queueMention full body + where target/queueId is set (10707000..10711400)."""
BUNDLE = "/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js"
data = open(BUNDLE, 'rb').read()
print(data[10707000:10711400].decode('utf-8', 'replace'))
