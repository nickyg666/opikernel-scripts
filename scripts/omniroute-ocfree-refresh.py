#!/usr/bin/env python3
"""omniroute-ocfree-refresh.py — keep the oc-free combo real AND serving.

What it does (idempotent, prints only on change):
 1. Asks upstream https://opencode.ai/zen/v1/models for the LIVE free-model id list
    (ids containing 'free').
 2. Ensures the keyless `opencode` connection carries the pseudo-account pool
    (one fingerprint+proxyId pair per ACTIVE proxy in proxy_registry) so each
    request egresses from a rotated IP with no API key tied to it.
 3. HEALTH-FILTERS the free ids: each candidate is probed DIRECT keyless from this
    host against the upstream chat endpoint. Upstream verdicts:
        200/429/403  -> KEEP   (model exists; 429 = allowance spent, 403 = our IP
                                 flagged, both recover without config change)
        400 "Model is unavailable" / 500 / timeouts-with-empty-model -> DROP
                                 (model itself is broken/unlisted upstream)
    Dropped ids are recorded in state/ocfree-dropped.json with reason + timestamp and
    re-tested every run, so a model that comes back upstream is auto-restored.
 4. Rewrites combo 'oc-free' to EXACTLY the serving free ids on provider 'opencode'.
 5. One heartbeat through the router.

cron: hourly (see crontab), flock-guarded.
"""
import concurrent.futures
import json
import os
import sqlite3
import subprocess
import sys
import time

DB = "/var/lib/omniroute/storage.sqlite"
COMBO = "oc-free"
PROVIDER = "opencode"
MODELS_URL = "https://opencode.ai/zen/v1/models"
CHAT_URL = "https://opencode.ai/zen/v1/chat/completions"
ROUTER = "http://127.0.0.1:20128"
STATE_DIR = "/home/host/opikernel/state"
DROPPED_FILE = os.path.join(STATE_DIR, "ocfree-dropped.json")
CHANGES = []


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def upstream_free_ids():
    try:
        out = subprocess.run(["curl", "-s", "-m", "20", MODELS_URL], capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout)["data"]
        return sorted(m["id"] for m in data if "free" in m.get("id", ""))
    except Exception as e:
        print(f"ocfree: WARN upstream models fetch failed: {e}", flush=True)
        return None


def probe_model(mid):
    """Direct keyless probe. Returns (verdict, detail)."""
    body = json.dumps({"model": mid, "max_tokens": 4, "messages": [{"role": "user", "content": "hi"}]})
    try:
        p = subprocess.run(["curl", "-s", "-m", "25", "-o", "/tmp/ocf_hc.json", "-w", "%{http_code}",
                            "-H", "content-type: application/json", "-d", body, CHAT_URL],
                           capture_output=True, text=True, timeout=35)
        code = p.stdout.strip() or "000"
    except Exception:
        return "TIMEOUT", "curl timeout"
    etype = ""
    try:
        d = json.load(open("/tmp/ocf_hc.json"))
        if "choices" in d:
            return "OK", "200 served"
        etype = d.get("error", {}).get("type", "")
    except Exception:
        pass
    if code == "429":
        return "KEEP", "429 allowance spent (recovers)"
    if code == "403":
        return "KEEP", "403 IP-flagged (model exists)"
    if code == "400":
        return "DROP", "400 model unavailable"
    if code == "500":
        return "DROP", "500 upstream broken"
    return "DROP", f"{code} {etype}".strip()


def health_filter(ids):
    """Probe concurrently; returns (kept, dropped{mid:(reason,ts)})."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = dict(zip(ids, ex.map(probe_model, ids)))
    kept = [m for m in ids if results[m][0] in ("OK", "KEEP")]
    dropped = {m: (det, now_iso()) for m, (v, det) in results.items() if v == "DROP"}
    return kept, dropped


def main():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row

    live = upstream_free_ids()
    if live is None:
        return 1

    # ---- 1. pseudo-account pool on the keyless opencode connection(s) --------
    proxies = [r["id"] for r in con.execute("SELECT id FROM proxy_registry WHERE status='active' ORDER BY host")]
    for conn in con.execute("SELECT id,api_key,provider_specific_data FROM provider_connections WHERE provider=?", (PROVIDER,)):
        psd = json.loads(conn["provider_specific_data"] or "{}")
        keyed = bool(conn["api_key"])
        old = [e for e in (psd.get("accountProxies") or []) if isinstance(e, dict) and e.get("proxyId") in set(proxies)]
        seen = {e.get("proxyId") for e in old}
        for pid in proxies:
            if pid not in seen:
                old.append({"fingerprint": os.urandom(16).hex(), "proxyId": pid})
                seen.add(pid)
        want_fps = [e["fingerprint"] for e in old]
        if not keyed and want_fps != (psd.get("fingerprints") or []):
            psd["fingerprints"] = want_fps
            psd["accountProxies"] = old
            con.execute("UPDATE provider_connections SET provider_specific_data=?, updated_at=? WHERE id=?",
                        (json.dumps(psd), now_iso(), conn["id"]))
            CHANGES.append(f"{conn['id'][:8]}: pseudo-account pool -> {len(old)} (keyless, one per live proxy)")

    # ---- 2. health-filter the free ids --------------------------------------
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        prev_dropped = json.load(open(DROPPED_FILE))
    except Exception:
        prev_dropped = {}
    kept, dropped = health_filter(live)
    merged_dropped = {m: v for m, v in prev_dropped.items() if m in live and m in dropped}
    for m, v in dropped.items():
        merged_dropped[m] = v
    restored = [m for m in live if m in prev_dropped and m in kept]
    new_drops = [m for m in dropped if m not in prev_dropped]
    if new_drops:
        CHANGES.append(f"health: DROPPED {new_drops} "
                       f"({ '; '.join(f'{m}: {dropped[m][0]}' for m in new_drops) })")
    if restored:
        CHANGES.append(f"health: RESTORED {restored} (back upstream)")
    if merged_dropped != prev_dropped:
        json.dump(merged_dropped, open(DROPPED_FILE, "w"), indent=1)

    # ---- 3. combo 'oc-free' = serving free ids on provider opencode ---------
    row = con.execute("SELECT id,data FROM combos WHERE name=?", (COMBO,)).fetchone()

    def mk(mid):
        return {"id": "ocfree-" + mid.replace("/", "-").replace(".", "_").replace(":", "_"),
                "kind": "model", "model": f"{PROVIDER}/{mid}", "providerId": PROVIDER, "weight": 0}

    want_models = [mk(m) for m in kept]
    if not want_models:
        CHANGES.append("WARN: zero serving free models — combo left untouched")
    elif row is None:
        data = {"name": COMBO, "description": "opencode free tier only (auto-refreshed + health-filtered)",
                "models": want_models, "strategy": "priority",
                "config": {"strategy": "priority", "maxRetries": 4, "retryDelayMs": 700,
                           "targetTimeoutMs": 90000, "concurrencyPerModel": 1,
                           "compatFilterFailOpen": True, "candidatePool": [PROVIDER]},
                "isHidden": False, "sortOrder": 3, "version": 1, "createdAt": now_iso(), "updatedAt": now_iso()}
        con.execute("INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (os.urandom(16).hex(), COMBO, json.dumps(data, separators=(",", ":")), 3,
                     data["createdAt"], data["updatedAt"]))
        CHANGES.append(f"combo {COMBO} CREATED with {len(want_models)} serving free models")
    else:
        cid, data = row["id"], json.loads(row["data"])
        cur = [m["model"].split("/", 1)[1] for m in data.get("models", [])]
        if cur != kept:
            data["models"] = want_models
            data["config"]["strategy"] = "priority"
            data["config"]["candidatePool"] = [PROVIDER]
            data["config"]["compatFilterFailOpen"] = True
            data["version"] = int(data.get("version", 1)) + 1
            data["updatedAt"] = now_iso()
            con.execute("UPDATE combos SET data=?, updated_at=? WHERE id=?",
                        (json.dumps(data, separators=(",", ":")), data["updatedAt"], cid))
            CHANGES.append(f"combo {COMBO}: {len(cur)} -> {len(kept)} serving models "
                           f"(+{sorted(set(kept)-set(cur))} -{sorted(set(cur)-set(kept))})")

    con.commit()
    con.close()

    # ---- 4. heartbeat through the router (only if we have candidates) -------
    if kept:
        key_row = sqlite3.connect(DB).execute("SELECT key FROM api_keys WHERE id='test-key-1'").fetchone()
        if key_row:
            body = json.dumps({"model": f"{PROVIDER}/{kept[0]}", "max_tokens": 4,
                               "messages": [{"role": "user", "content": "hi"}]})
            out = subprocess.run(["curl", "-s", "-m", "140", "-o", "/dev/null", "-w", "%{http_code}",
                                  "-H", "Authorization: Bearer " + key_row[0],
                                  "-H", "Content-Type: application/json", "-d", body,
                                  ROUTER + "/v1/chat/completions"], capture_output=True, text=True, timeout=150)
            CHANGES.append(f"heartbeat {kept[0]} via router: HTTP {out.stdout.strip() or '000'}")

    for c in CHANGES:
        print("ocfree:", c, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
