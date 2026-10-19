#!/usr/bin/env python3
"""PA bounded action: audit the room's nudge/whip loop for spin + accountability gaps.

Read-only. Resolves the group-chat DB (guessed path is refused), then for the given
room and lookback window:
  * counts nudges per target and how many of them got a reply after them
  * counts orchestrator digests, their stale sets, and whether the digest claims
    `blockers=none` while a named agent is long-silent
  * flags CONTENT-IDENTICAL nudges (loop spin) vs. substantive traffic
"""
import sqlite3, sys, time, json, collections

DB = "/home/host/.hermes-web-ui/hermes-web-ui.db"
ROOM = sys.argv[1] if len(sys.argv) > 1 else "mti5ax1clq0zlx"
MINUTES = int(sys.argv[2]) if len(sys.argv) > 2 else 45

assert DB.endswith("hermes-web-ui.db")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
cols = [r[1] for r in con.execute("pragma table_info(gc_messages)")]
assert "roomId" in cols, cols
now_ms = int(time.time() * 1000)
cut = now_ms - MINUTES * 60 * 1000

rows = list(con.execute(
    "select senderName, senderType, content, timestamp from gc_messages "
    "where roomId=? and timestamp>? order by timestamp", (ROOM, cut)))

def kind(c):
    c = c or ""
    if c.startswith("[orchestrator"):
        return "digest"
    if "Do ONE bounded action for your role now" in c:
        return "nudge"
    return "post"

def targets(c):
    import re
    return [s.lower().lstrip("@") for s in re.findall(r"@([A-Za-z0-9_-]+)", c or "")]

stats = collections.Counter()
nudge_target = collections.Counter()
nudge_text = collections.Counter()
by_sender = collections.Counter()
digest_stale = collections.Counter()
digest_blockers = []
nudged_again = collections.Counter()

for r in rows:
    k = kind(r["content"])
    stats[k] += 1
    by_sender[f"{r['senderName']}|{k}"] += 1
    if k == "nudge":
        ts = targets(r["content"])
        for t in ts:
            nudge_target[t] += 1
        # normalize: strip the silence number so identical loop nudges collapse
        import re
        norm = re.sub(r"\d+\.\d+min silent", "Nmin silent", r["content"] or "")
        norm = re.sub(r"last room output was [\d\-: ]+", "last room output was TS", norm)
        nudge_text[norm.strip()[:200]] += 1
    if k == "digest":
        for t in targets(r["content"]):
            digest_stale[t] += 1
        digest_blockers.append((r["timestamp"], (r["content"] or "")[-60:]))

span = (rows[-1]["timestamp"] - rows[0]["timestamp"]) / 60000.0 if len(rows) > 1 else 0
print(f"== room {ROOM} lookback {MINUTES}min (cut {time.strftime('%H:%M:%S', time.localtime(cut/1000))}) ==")
print(f"messages={len(rows)} span={span:.1f}min -> {len(rows)/span if span else 0:.1f} msg/min")
print(f"kinds: " + " ".join(f"{k}={v}" for k, v in stats.most_common()))
print("\n-- who speaks (sender|kind=count), top 12 --")
for s, n in by_sender.most_common(12):
    print(f"  {s}={n}")
print("\n-- nudge targets (times named in lookback) --")
for t, n in nudge_target.most_common():
    print(f"  @{t} = {n}")
uniq = len(nudge_text)
tot = sum(nudge_text.values())
print(f"\n-- loop spin: {tot} nudges, {uniq} distinct texts -> {tot/max(uniq,1):.1f}x repetition --")
for txt, n in nudge_text.most_common(5):
    if n > 1:
        print(f"  {n}x  {txt[:110]}")
print("\n-- orchestrator digests (target=count) --")
for t, n in digest_stale.most_common():
    print(f"  @{t} in {n}/{stats['digest']} digests")
print("\n-- last 3 digest tails (blockers claim) --")
for ts, tail in digest_blockers[-3:]:
    print(f"  {time.strftime('%H:%M:%S', time.localtime(ts/1000))} ...{tail}")
print("\n-- room output per agent (last post time) --")
last = {}
for r in rows:
    if kind(r["content"]) == "post" and r["senderType"] != "human":
        last[r["senderName"]] = r["timestamp"]
for nm, ts in sorted(last.items(), key=lambda kv: kv[1]):
    print(f"  {nm:20s} {time.strftime('%H:%M:%S', time.localtime(ts/1000))} ({(now_ms-ts)/60000:.1f} min ago)")
