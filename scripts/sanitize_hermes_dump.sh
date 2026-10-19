#!/usr/bin/env bash
# sanitize_hermes_dump.sh — build a secrets-free hermes-private dump
set -euo pipefail

SRC=/home/host/.hermes
DST=/home/host/hermes-private-dump
TS=$(date +%Y%m%d-%H%M%S)

rm -rf "$DST"
mkdir -p "$DST"/{config,plugins,skills,memories,cron,scripts}

# ---- config.yaml: redact known secret values, keep structure ----
sed -e 's/HA_TOKEN: .*/HA_TOKEN: REDACTED/' \
    -e 's/secret: f54213cf67dd7cbce1416eaf60512c9c9988719850573eef/secret: REDACTED/' \
    -e 's/^\( *\)password: 1$/\1password: REDACTED/' \
    -e 's/api_key: .*/api_key: REDACTED/' \
    "$SRC/config.yaml" > "$DST/config/config.yaml"

# ---- .env: NEVER push raw. Ship a template with names only. ----
grep -oE '^[A-Z_]+' "$SRC/.env" | sort -u > "$DST/config/.env.keys"
echo "# values redacted — see host ~/.hermes/.env" >> "$DST/config/.env.keys"

# ---- auth.json: redact any long token-ish values ----
python3 - "$SRC/auth.json" "$DST/config/auth.json" <<'EOF'
import json, re, sys
src, dst = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(src))
    def scrub(o):
        if isinstance(o, dict):
            return {k: ("REDACTED" if any(s in k.lower() for s in ("token","key","secret","password","access")) and isinstance(v,str) and len(v)>8 else scrub(v)) for k,v in o.items()}
        if isinstance(o, list):
            return [scrub(x) for x in o]
        return o
    json.dump(scrub(d), open(dst,"w"), indent=2)
except Exception as e:
    open(dst,"w").write(f"{{}}  # scrub failed: {e}")
EOF

# ---- plugins / cron / scripts: plain copy (scan below) ----
cp -a "$SRC/plugins/." "$DST/plugins/"
cp -a "$SRC/cron/jobs.json" "$DST/cron/" 2>/dev/null || true
cp -a "$SRC/scripts/." "$DST/scripts/" 2>/dev/null || true

# ---- skills: copy, then scrub real secret-looking values across all text ----
cp -a "$SRC/skills/." "$DST/skills/"
find "$DST" -type f \( -name '*.md' -o -name '*.py' -o -name '*.sh' -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' -o -name '*.txt' \) -print0 | \
while IFS= read -r -d '' f; do
  python3 - "$f" <<'EOF'
import re, sys
p = sys.argv[1]
try:
    s = open(p, encoding='utf-8', errors='replace').read()
except Exception:
    sys.exit(0)
orig = s
# GitHub PATs
s = re.sub(r'ghp_[A-Za-z0-9]{20,}', 'ghp_REDACTED', s)
s = re.sub(r'github_pat_[A-Za-z0-9_]{20,}', 'github_pat_REDACTED', s)
# long base64/JWT-ish blobs (>=32 chars, token-like)
s = re.sub(r'(?i)\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b', 'REDACTED_JWT', s)
s = re.sub(r'(?i)\b(token|api[_-]?key|secret|password)\s*[=:]\s*["\']?[A-Za-z0-9_\-\.]{16,}["\']?', r'\1: REDACTED', s)
# known NAS/DAS passwords
s = s.replace('REDACTED_NAS_PW', 'NAS_PW_REDACTED')
if s != orig:
    open(p, 'w', encoding='utf-8').write(s)
EOF
done

# ---- memories: copy + scrub token-ish lines (keep lab creds, they're local-only) ----
cp -a "$SRC/memories/MEMORY.md" "$DST/memories/"
python3 - "$DST/memories/MEMORY.md" <<'EOF'
import re, sys
p = sys.argv[1]
s = open(p, encoding='utf-8', errors='replace').read()
s = re.sub(r'ghp_[A-Za-z0-9]{20,}', 'ghp_REDACTED', s)
s = re.sub(r'\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b', 'REDACTED_JWT', s)
s = s.replace('REDACTED_NAS_PW', 'NAS_PW_REDACTED')
open(p, 'w', encoding='utf-8').write(s)
EOF

# ---- SOUL + README ----
cp -a "$SRC/SOUL.md" "$DST/"
cat > "$DST/README.md" <<EOF
# hermes-private

Sanitized private backup of the Hermes agent runtime (host .168), $TS.

Contains: config.yaml (secrets redacted), .env key NAMES only (values live on
host ~/.hermes/.env), auth.json (redacted), plugins/, skills/, memories/
(MEMORY.md — lab-local creds kept, external secrets redacted), cron/jobs.json,
scripts/, SOUL.md.

REDACTED markers: HA_TOKEN, webhook secret, GitHub PATs, JWTs, NAS/DAS
passwords, api_keys. This repo is PRIVATE — do not add real secrets.
EOF

# ---- leftover secret scan (should print nothing) ----
echo "=== leftover scan ==="
grep -rlEi 'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|REDACTED_NAS_PW|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}' "$DST" 2>/dev/null | head -10 || true
echo "=== dump size ==="
du -sh "$DST"
echo "=== tree ==="
ls "$DST"
