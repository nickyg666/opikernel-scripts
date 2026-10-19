import json
d = json.load(open('/home/host/.hermes/cron/jobs.json'))
if isinstance(d, dict):
    d = d.get('jobs', [])
for j in d:
    if isinstance(j, str):
        try:
            j = json.loads(j)
        except Exception:
            continue
    if not isinstance(j, dict):
        continue
    if j.get('name') == 'va39-gate-watch':
        print("PROMPT:")
        print(j.get('prompt'))
        print("--- schedule:", j.get('schedule'))
        print("--- no_agent:", j.get('no_agent'), "script:", j.get('script'), "model:", j.get('model'))
