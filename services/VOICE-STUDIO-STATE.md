# Pocket Voice Studio — state as of 2026-10-01

## It was never lost. It was invisible.

Long gap where this looked like abandoned work. It was running the whole
time; nobody had asked whether the ports were up.

## Live, right now

| thing | state |
|---|---|
| `pocket-tts.service` | active — Kyutai PocketTTS 2.1.0, `127.0.0.1:8021` |
| `pocket-voice-studio.service` | active — panel on `127.0.0.1:8092` |
| public route | `https://192.168.0.168/voice-studio/` → 200, via Caddy |
| voices cloned | nick, nick-quick, nick-blended, nick-scripted, sage, sageygud, lorenzo, cosby |
| generation | POST `/api/generate` (form fields `text`, `voice`) → 24kHz mono WAV, ~3s of audio in ~12s |

The panel has no `/health` route (404 is expected); use `GET /` on 8092, or
`/health` on 8021 for the backend.

## The real bug: every WAV declared ~11.5 hours

`pocket_tts/data/audio.py` (2.1.0):

    write_header():  wave_writer.setnframes(1_000_000_000)     # placeholder
    finalize():      wave_writer._patchheader = lambda: None  # disables fixup

The placeholder frame count is never corrected. A 3.4s clip reported
**41,666 seconds**. Python's `wave` module tolerates that on read, which is
exactly why it went unnoticed for a year. `ffmpeg`/`ffprobe` and any audiobook
muxer read the header instead of the bytes and get it badly wrong.

Fixed in `_fix_wav_header()` in the panel, on the way out. Verified:
41,666.7s → 3.24s, header matches actual audio exactly, **8 header bytes
changed, PCM payload bit-identical**, `ffprobe` agrees, and a full transcode
drops from "try to process 11.5 hours" to 0.19s.

Fixed at the panel boundary, NOT in site-packages: a pip upgrade would
silently undo it and version control would never see it.

## Source control was the second defect

`opikernel/services/` had **0 tracked files** and was not gitignored — simply
never added. The live panel had drifted 50 lines from the GitHub copy
(`nickyg666/hermes-pocket-tts-panel` @ `34aefe7`, one commit, Aug 25), so the
running program and the "backup" were different files, and the header fix
existed on exactly one machine.

Now: opikernel commit `7289ec9` tracks the panel and both launchers (local
repo — it has no remote, by design), and the GitHub repo is at `54f0a0e` with
the live 417-line file, the fix, and `systemd/pocket-voice-studio.service`
which the README referenced but which had never been committed.

## The audiobook gap is still real

Nothing converts EPUB → audiobook. The backend exposes exactly two endpoints
(`//health`, `//tts`) and can speak text; it has no notion of a book. Built
so far: voice cloning, a recorder UI, and a voice library. Still to build:
EPUB parse → chapter split → per-voice synthesis → M4B with ID3 chapter
markers → hook into the GoodBooks send path.

This is a feature, not a port, and it needs a call on where it lives: in
GoodBooks, or beside the studio.

## Gotchas

- `POST :8021/tts` takes **form fields**, not JSON, and the path in
  openapi.json appears as `//tts` (server mounts with a trailing-slash
  prefix). A JSON body returns 404/415 and looks like the service is broken.
- A stale `.git/index.lock` in opikernel silently made `git add` a no-op with
  a zero exit code. Check for it if staging comes back empty.
