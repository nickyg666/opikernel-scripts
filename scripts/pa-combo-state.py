
import sqlite3, json, time
# combo live state
c = sqlite3.connect("file:/var/lib/omniroute/storage.sqlite?mode=ro", uri=True)
cur = c.cursor()
for name, data, typ, upd in cur.execute("select name, data, typeof(data), updated_at from combos where name like '%freeAF%'"):
    try:
        d = json.loads(data)
        ms = [m if isinstance(m,str) else (m.get("model") or m.get("id") or str(m)) for m in d.get("models", [])]
    except Exception as e:
        ms = ["PARSE_ERR:%s" % e]
    print("COMBO %s typeof=%s updated_at=%s n=%d" % (name, typ, upd, len(ms)))
    for i, m in enumerate(ms):
        print("   [%02d] %s" % (i, m))
# timing of the omni 401 bodies
g = sqlite3.connect("file:/home/host/.hermes-web-ui/hermes-web-ui.db?mode=ro", uri=True)
gc = g.cursor()
for ts, s in gc.execute("select timestamp, senderName from gc_messages where roomId='mti5ax1clq0zlx' and content like '%No active credentials for provider: omni%' and julianday(timestamp/1000.0,'unixepoch') > julianday('now','-60 minutes') order by timestamp"):
    print("OMNI401", time.strftime("%H:%M:%S", time.localtime(ts/1000.0)), s)
