#!/bin/bash
# PA combo target re-probe — read-only. Never prints the API key.
# Usage: bash scripts/pa-combo-reprobe.sh [combo-name]
COMBO="${1:-omni/freeAF}"
DB="file:/var/lib/omniroute/storage.sqlite?mode=ro"
KEY=$(sudo -n sqlite3 "$DB" "select key from api_keys where name='Hermes Integration';" 2>/dev/null)
[ -z "$KEY" ] && { echo "FATAL: no key"; exit 1; }
TMP=$(mktemp)
sudo -n sqlite3 "$DB" "select data from combos where name='$COMBO';" > "$TMP" 2>/dev/null
mapfile -t MODELS < <(python3 - "$TMP" <<'PY'
import sys,json
d=json.load(open(sys.argv[1]))
for t in (d.get('models') or d.get('targets') or []):
    print(t.get('model') if isinstance(t,dict) else t)
PY
)
rm -f "$TMP"
printf '%-8s %s\n' "== $COMBO ($(date '+%H:%M:%S')) ==" ""
for i in "${!MODELS[@]}"; do
  m="${MODELS[$i]}"
  [ -z "$m" ] && continue
  B=$(mktemp)
  R=$(curl -s -o "$B" -w '%{http_code} %{time_total}' --max-time 25 \
      -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":1}" \
      http://127.0.0.1:20128/v1/chat/completions 2>/dev/null)
  ERR=$(head -c 100 "$B" | tr -d '\n' | tr -s ' ')
  rm -f "$B"
  printf '[%2d] %-50s %s | %s\n' "$i" "$m" "$R" "$ERR"
done
