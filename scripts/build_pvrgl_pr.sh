#!/bin/bash
# build_pvrgl_pr.sh — build PR branch (main + 1 commit of pvrgl files) and push.
set -e
SRC=/home/host/mesa-scratch
STAGE=/home/host/opikernel/stage/pvrgl-pr
TOKEN=$(sed -n 1p /home/host/github_PAT)
URL="https://nickyg666:${TOKEN}@github.com/nickyg666/mesa-pvrgl.git"

rm -rf "$STAGE"
mkdir -p "$STAGE"

# Extract exactly the files changed by the pvrgl work.
cd "$SRC"
git diff --name-only d2d9722..pvrgl-m2 | while read -r f; do
  mkdir -p "$STAGE/$(dirname "$f")"
  git show "pvrgl-m2:$f" > "$STAGE/$f"
done

cd "$STAGE"
git init -q
git remote add github "$URL"
git fetch -q github main
git checkout -q -b pr github/main
git add -A
git -c user.name="nickyg666" -c user.email="nickyg666@users.noreply.github.com" commit -q -m "pvrgl: native PowerVR Gallium GL driver for Orange Pi Zero 3W

Open-source hardware GL for PowerVR BXM-4-64 (no zink/llvmpipe):
- M1: kernel ABI probe, winsys path, TRANSFER_FRAG context + BO/vma plumbing
- M2: TQ hardware clear backend — EGL glClear pixel proof (ff 00 00 ff @32,32)
- M3-P1: render path — free lists, HWRT dataset, RENDER context,
  geometry/fragment fw streams, render_submit (submit ENOENT hunt in flight)

30 files: src/gallium/drivers/pvrgl/ (driver), meson wiring, pipe-loader
integration, winsys probe + transfer job fixes."
git push -q github pr:refs/heads/pvrgl-m2
echo "pushed pvrgl-m2"
git rev-parse HEAD
