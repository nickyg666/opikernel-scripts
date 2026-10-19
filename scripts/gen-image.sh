#!/usr/bin/env bash
# Text-to-image via the lab omni router (192.168.0.168:20128) /v1/images/generations.
# Usage: gen-image.sh <model> <outfile> <prompt> [size]
# Models verified live 2026-09-27:
#   openrouter/google/gemini-3-pro-image-preview
#   openrouter/openai/gpt-5-image-mini
#   nvidia/black-forest-labs/flux.2-klein-4b
# apikey.fan / fun-codex are 403 INSUFFICIENT_BALANCE -- do not bother.
set -euo pipefail
MODEL="$1"; OUT="$2"; PROMPT="$3"; SIZE="${4:-1024x1024}"
ROUTE="${OMNI_ROUTE:-http://192.168.0.168:20128}"
KEY="${OMNI_KEY:-ombqroute-hermes-123}"
TMP="$(mktemp /tmp/genimg.XXXXXX.json)"; trap 'rm -f "$TMP"' EXIT
curl -sS --max-time 300 "$ROUTE/v1/images/generations" \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"model":sys.argv[1],"prompt":sys.argv[2],"size":sys.argv[3],"n":1}))' "$MODEL" "$PROMPT" "$SIZE")" \
  -o "$TMP"
python3 - "$TMP" "$OUT" "$MODEL" <<'PY'
import base64, json, os, sys
d = json.load(open(sys.argv[1]))
if "error" in d:
    sys.exit("UPSTREAM_ERR: " + json.dumps(d["error"])[:400])
item = d["data"][0]
if item.get("b64_json"):
    b = base64.b64decode(item["b64_json"])
elif item.get("url"):
    import urllib.request
    b = urllib.request.urlopen(item["url"], timeout=120).read()
else:
    sys.exit("NO_IMAGE_IN_RESPONSE: " + json.dumps(item)[:300])
# Trust the BYTES, not the request/response field: these routes return JPEG
# under a "png" extension often enough to break every viewer.
ext = {b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png", b"GIF8": ".gif",
       b"RIFF": ".webp", b"BM": ".bmp"}.get(b[:3], ".png")
out = os.path.splitext(sys.argv[2])[0] + ext
open(out, "wb").write(b)
print(f"OK model={sys.argv[3]} bytes={len(b)} -> {out}")
PY
