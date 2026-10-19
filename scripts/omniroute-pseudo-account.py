#!/usr/bin/env python3
"""omniroute-pseudo-account.py — add API keys and/or pseudo-account identities to
an OmniRoute provider connection.

Mechanism (verified in the shipped bundle 2026-09-20):
  * providerSpecificData.extraApiKeys[] -> the router rotates the outbound bearer
    per request:  apiKey && connectionId && extraApiKeys.length
                    ? getRotatingApiKey(connectionId, apiKey, extraApiKeys)
                    : apiKey
    So "more keys" = more accounts in the rotation, no UI needed.
  * providerSpecificData.fingerprints[] + providerSpecificData.accountProxies[]
    ({fingerprint, proxyId}) -> an ACCOUNT POOL: one pseudo-account per
    fingerprint, each bound to its own egress proxy, cycled round-robin with
    its own cooldownUntil / consecutiveFails. More entries = more parallel
    identities + more egress IPs.

What it does (idempotent, deduped by sha256 of the key / by fingerprint):
  --key / --key-file      append one or more keys to extraApiKeys
  --add-pseudo N          append N pseudo-account identities, each bound to the
                          next unused ACTIVE proxy from proxy_registry
  --list                  show the current key/pseudo-account state (no secrets)
  --dry-run               print the plan, write nothing

Examples
  ./omniroute-pseudo-account.py --provider opencode-zen --list
  ./omniroute-pseudo-account.py --provider opencode-zen --key-file /tmp/new.key
  ./omniroute-pseudo-account.py --provider opencode --add-pseudo 7
"""
import argparse
import hashlib
import json
import sqlite3
import sys
import uuid

DB = "/var/lib/omniroute/storage.sqlite"


def sha(s: str) -> str:
    return hashlib.sha256(s.strip().encode()).hexdigest()[:12]


def load(con, provider):
    row = con.execute(
        "SELECT id, provider, name, api_key, provider_specific_data FROM provider_connections WHERE provider=?",
        (provider,)).fetchone()
    if not row:
        sys.exit(f"no connection for provider {provider!r}")
    psd = {}
    if row[4]:
        try:
            psd = json.loads(row[4])
        except Exception:
            sys.exit(f"provider_specific_data for {provider} is not JSON — refusing to touch it")
    return {"id": row[0], "provider": row[1], "name": row[2], "api_key": row[3], "psd": psd}


def active_proxies(con):
    return [r[0] for r in con.execute("SELECT id FROM proxy_registry WHERE status='active' ORDER BY host")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True)
    ap.add_argument("--key", action="append", default=[])
    ap.add_argument("--key-file", action="append", default=[])
    ap.add_argument("--add-pseudo", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", default=DB)
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    c = load(con, a.provider)
    psd = c["psd"]
    keys = list(psd.get("extraApiKeys") or [])
    fps = list(psd.get("fingerprints") or [])
    aps = list(psd.get("accountProxies") or [])

    if a.list:
        print(f"{a.provider}: connection {c['id']}")
        print(f"  primary apiKey: {'set (' + sha(c['api_key']) + ')' if c['api_key'] else 'NONE'}")
        print(f"  extraApiKeys : {[sha(k) for k in keys]}")
        print(f"  fingerprints : {len(fps)} {fps[:3]}{' ...' if len(fps) > 3 else ''}")
        print(f"  accountProxies: {len(aps)}")
        print(f"  rotation active: {bool(c['api_key'] and c['id'] and keys)}")
        return 0

    new_keys = list(a.key)
    for p in a.key_file:
        new_keys += [line.strip() for line in open(p) if line.strip()]
    added_keys = []
    for k in new_keys:
        if sha(k) in [sha(x) for x in keys]:
            continue
        keys.append(k)
        added_keys.append(sha(k))

    used_proxy_ids = {e.get("proxyId") for e in aps if isinstance(e, dict)}
    pool = [p for p in active_proxies(con) if p not in used_proxy_ids]
    added_fp = []
    for i in range(a.add_pseudo):
        fp = uuid.uuid4().hex
        pid = pool[i] if i < len(pool) else (active_proxies(con)[i % max(1, len(active_proxies(con)))] if active_proxies(con) else None)
        fps.append(fp)
        aps.append({"fingerprint": fp, "proxyId": pid})
        added_fp.append((fp[:8], pid[:8] if pid else None))

    if not added_keys and not added_fp:
        print(f"{a.provider}: nothing to do (already present / no proxies available)")
        return 0

    psd["extraApiKeys"] = keys
    psd["fingerprints"] = fps
    psd["accountProxies"] = aps
    print(f"{a.provider}: +{len(added_keys)} key(s) {added_keys}, +{len(added_fp)} pseudo-account(s) {added_fp}")
    print(f"  totals -> extraApiKeys={len(keys)} fingerprints={len(fps)} accountProxies={len(aps)}")
    if a.dry_run:
        print("  (dry run — nothing written)")
        return 0
    con.execute("UPDATE provider_connections SET provider_specific_data=? WHERE id=?", (json.dumps(psd), c["id"]))
    con.commit()
    print("  written. Router reads connections per request; no restart needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
