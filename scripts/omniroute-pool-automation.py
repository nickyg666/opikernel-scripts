#!/usr/bin/env python3
"""omniroute-pool-automation.py — keep OmniRoute's free-lane plumbing self-healing.

Nick's model: proxies == wireguard == "get a different IP". Each fresh IP is worth
usage, so the pool must stay alive and the account pools must always point at live
proxies — without anyone touching a dashboard.

Does FOUR things, in order, and only prints when something changed:

 1. PROXY REVALIDATION — every `proxy_registry` row is probed through its own socks5
    (neutral HTTPS target). Unreachable -> status='dead' + removed from every
    `proxy_assignments` row. Previously dead rows that answer -> status='active'.
 2. ACCOUNT-POOL SYNC — for every provider connection that carries `fingerprints` +
    `accountProxies` (the pseudo-account pool: one identity per egress), rebuild the
    pool to exactly the live proxy set, preserving existing pairs where the proxy is
    still alive. Adds `extraApiKeys` rotation only when keys are supplied.
 3. LOCK RECOVERY — for providers in EGRESS_BUCKETED_LOCK_PROVIDERS (opencode,
    opencode-go, opencode-cli) plus opencode-zen, a stale `rate_limited_until` in the
    future is retested against the router's own provider test; if the provider answers,
    the lock is cleared (it was written from a single 429's reset window and otherwise
    benches the lane for days).
 4. COMBO GUARD — a priority combo whose top-level `strategy` says "auto" runs the auto
    candidate selector and can 503 every tool-carrying request
    ("all targets were skipped by pre-dispatch filters"); force data.strategy to match
    config.strategy. Also re-points the openrouter account scope at the live pool.

Exit 0 always (cron-friendly); state changes are logged to stdout.
"""
import concurrent.futures
import json
import os
import sqlite3
import subprocess
import sys
import time

DB = "/var/lib/omniroute/storage.sqlite"
ROUTER = "http://127.0.0.1:20128"
PROBE_TARGET = "https://api.ipify.org"
PERFIX_PROVIDERS = ("opencode", "opencode-go", "opencode-zen", "openrouter")
LOCK_PROVIDERS = ("opencode", "opencode-go", "opencode-zen", "opencode-cli")
PRIORITY_COMBOS = ("omni/freeAF",)
changes = []


def q(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def x(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def router_key():
    r = q("SELECT key FROM api_keys WHERE id='test-key-1'")
    return r[0]["key"] if r else ""


def probe_proxy(p):
    proxy = f"socks5h://{p['username']}:{p['password']}@{p['host']}:{p['port']}"
    try:
        out = subprocess.run(["curl", "-s", "-m", "10", "-o", "/dev/null", "-w", "%{http_code}",
                              "-x", proxy, PROBE_TARGET], capture_output=True, text=True, timeout=20)
        return p["id"], (out.stdout.strip() in ("200", "301", "302"))
    except Exception:
        return p["id"], False


def step1_proxies():
    rows = q("SELECT id,host,port,username,password,status FROM proxy_registry")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = dict(ex.map(probe_proxy, rows))
    live = []
    for r in rows:
        ok = results.get(r["id"], False)
        if ok and r["status"] != "active":
            x("UPDATE proxy_registry SET status='active', updated_at=? WHERE id=?", (now_iso(), r["id"]))
            changes.append(f"proxy {r['host']} revived -> active")
        if not ok and r["status"] == "active":
            x("UPDATE proxy_registry SET status='dead', updated_at=? WHERE id=?", (now_iso(), r["id"]))
            removed = x("DELETE FROM proxy_assignments WHERE proxy_id=?", (r["id"],))
            changes.append(f"proxy {r['host']} dead (assignments dropped: {removed})")
        if ok:
            live.append(r["id"])
    return live


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def step2_pools(live):
    if not live:
        changes.append("ACCOUNT POOLS: no live proxies — pool sync skipped")
        return
    live_set = set(live)
    for conn in q("SELECT id,provider,api_key,provider_specific_data FROM provider_connections WHERE is_active=1"):
        psd = {}
        try:
            psd = json.loads(conn["provider_specific_data"] or "{}")
        except Exception:
            continue
        if "accountProxies" not in psd and "fingerprints" not in psd:
            continue
        if psd.get("egressPolicy") == "direct_only":
            # Operator verdict: this provider's egresses must be flagged-clean, and every
            # pooled proxy was rejected upstream (e.g. opencode Console 403 on datacenter
            # IPs). Leave it direct and do not repopulate the pool.
            continue
        keyed = bool(conn["api_key"])
        if keyed:
            # Nick's rule: never tie the account key to proxied requests — a keyed lane
            # egresses direct; a rotated IP must be a KEYLESS identity.
            if psd.get("accountProxies") or psd.get("fingerprints"):
                psd["accountProxies"] = []
                psd["fingerprints"] = []
                psd["extraApiKeys"] = []
                x("UPDATE provider_connections SET provider_specific_data=?, updated_at=? WHERE id=?",
                  (json.dumps(psd), now_iso(), conn["id"]))
                changes.append(f"pool {conn['provider']}: CLEARED (keyed lane must egress direct)")
            continue
        old = [e for e in (psd.get("accountProxies") or []) if isinstance(e, dict) and e.get("proxyId") in live_set]
        seen = {e.get("proxyId") for e in old}
        for pid in live:
            if pid not in seen:
                old.append({"fingerprint": os.urandom(16).hex(), "proxyId": pid})
                seen.add(pid)
        new_fps = [e["fingerprint"] for e in old]
        if new_fps != (psd.get("fingerprints") or []):
            psd["fingerprints"] = new_fps
            psd["accountProxies"] = old
            x("UPDATE provider_connections SET provider_specific_data=?, updated_at=? WHERE id=?",
              (json.dumps(psd), now_iso(), conn["id"]))
            changes.append(f"pool {conn['provider']}: pseudo-accounts -> {len(old)} (live proxies, keyless)")


def step3_locks():
    key = router_key()
    for conn in q("SELECT id,provider,test_status,rate_limited_until FROM provider_connections WHERE provider IN (%s)"
                  % ",".join("'%s'" % p for p in LOCK_PROVIDERS)):
        locked = conn["rate_limited_until"] and conn["rate_limited_until"] > now_iso()
        if not locked and conn["test_status"] == "active":
            continue
        try:
            out = subprocess.run(["curl", "-s", "-m", "40", "-X", "POST",
                                  f"{ROUTER}/api/providers/{conn['id']}/test",
                                  "-H", f"Authorization: Bearer {key}"], capture_output=True, text=True, timeout=60)
            res = json.loads(out.stdout or "{}")
        except Exception as e:
            changes.append(f"test {conn['provider']} failed to run: {e}")
            continue
        ok = bool(res.get("success")) or bool(res.get("valid")) or res.get("status") in ("ok", "active", True)
        if ok:
            cleared = x("UPDATE provider_connections SET rate_limited_until=NULL, test_status='active',"
                        " last_error=NULL, last_error_type=NULL, error_code=NULL, backoff_level=0 WHERE id=?",
                        (conn["id"],))
            if cleared:
                changes.append(f"lock cleared for {conn['provider']} (provider test passed)")
        else:
            changes.append(f"{conn['provider']} still limited: {str(res)[:90]}")


def step4_combos(live):
    for name in PRIORITY_COMBOS:
        row = q("SELECT id,data FROM combos WHERE name=?", (name,))
        if not row:
            continue
        cid, data = row[0]["id"], json.loads(row[0]["data"])
        want = data.get("config", {}).get("strategy", "priority")
        if data.get("strategy") != want:
            data["strategy"] = want
            x("UPDATE combos SET data=?, updated_at=? WHERE id=?", (json.dumps(data, separators=(",", ":")), now_iso(), cid))
            changes.append(f"combo {name}: strategy {row[0]['data'][:60]!r} -> {want!r} (503 guard)")
    # openrouter account scope follows the live pool
    for conn in q("SELECT id FROM provider_connections WHERE provider='openrouter' AND is_active=1"):
        have = {r["proxy_id"] for r in q("SELECT proxy_id FROM proxy_assignments WHERE scope='account' AND scope_id=?", (conn["id"],))}
        want = set(live)
        if have != want:
            x("DELETE FROM proxy_assignments WHERE scope='account' AND scope_id=?", (conn["id"],))
            for i, pid in enumerate(live):
                x("INSERT INTO proxy_assignments (proxy_id,scope,scope_id,position,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                  (pid, "account", conn["id"], i, now_iso(), now_iso()))
            changes.append(f"openrouter account scope -> {len(live)} live proxies")


def step5_free_lane():
    """If the keyless opencode free lane starts answering, promote it in the combo."""
    key = router_key()
    body = json.dumps({"model": "opencode/mimo-v2.5-free", "max_tokens": 4,
                       "messages": [{"role": "user", "content": "hi"}]})
    try:
        out = subprocess.run(["curl", "-s", "-m", "30", "-o", "/tmp/free_lane.json", "-w", "%{http_code}",
                              f"{ROUTER}/v1/chat/completions", "-H", f"Authorization: Bearer {key}",
                              "-H", "Content-Type: application/json", "-d", body],
                             capture_output=True, text=True, timeout=45)
        state = out.stdout.strip()
    except Exception as e:
        changes.append(f"free-lane probe error: {e}")
        return
    if state != "200":
        return
    for name in PRIORITY_COMBOS:
        row = q("SELECT id,data FROM combos WHERE name=?", (name,))
        if not row:
            continue
        cid, data = row[0]["id"], json.loads(row[0]["data"])
        models = data.get("models", [])
        free_ids = [m for m in models if m.get("providerId") == "opencode"]
        if not free_ids or models[0].get("providerId") == "opencode":
            return
        rest = [m for m in models if m.get("providerId") != "opencode"]
        data["models"] = free_ids + rest
        x("UPDATE combos SET data=?, updated_at=? WHERE id=?",
          (json.dumps(data, separators=(",", ":")), now_iso(), cid))
        changes.append(f"FREE LANE UP: promoted {len(free_ids)} keyless opencode models to the top of {name}")


if __name__ == "__main__":
    live = step1_proxies()
    step2_pools(live)
    step3_locks()
    step4_combos(live)
    step5_free_lane()
    if changes:
        for c in changes:
            print("pool-automation:", c)
    sys.exit(0)
