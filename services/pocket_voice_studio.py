#!/usr/bin/env python3
"""Pocket Voice Studio — record-a-clip UI + voice library + TTS settings.

Serves on 127.0.0.1:8092.
- Static single-page app: mic recording (MediaRecorder -> webm/opus),
  preview playback, voice list, generation settings.
- POST /api/voices            upload clip -> normalize to 24k mono wav
- GET  /api/voices            list cloned voices
- DELETE /api/voices/{name}   remove a voice
- POST /api/generate          {text, voice} -> wav audio (proxied to pocket-tts serve :8000)
- GET/POST /api/settings      plugin playback/generation settings

Settings file: /home/host/.hermes/pocket-tts/settings.json
Voice library: /home/host/.hermes/pocket-tts/voices/<name>/reference.wav
"""
import json
import os
import struct
import shutil
import subprocess
import tempfile
import urllib.request
import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn

HOME = "/home/host"
BASE = f"{HOME}/.hermes/pocket-tts"
VOICES_DIR = f"{BASE}/voices"
SETTINGS_FILE = f"{BASE}/settings.json"
POCKET_URL = "http://127.0.0.1:8021/tts"

os.makedirs(VOICES_DIR, exist_ok=True)

DEFAULT_SETTINGS = {
    "engine_priority": ["pocket", "elevenlabs", "edge"],
    "pocket_voice": None,          # name of cloned voice for auto-notes
    "max_chars": 1200,
    "voice_notes_enabled": True,
    "voice_platforms": ["telegram"],
    "strip_markdown": True,
}


def _load_settings():
    try:
        s = json.load(open(SETTINGS_FILE))
        out = dict(DEFAULT_SETTINGS)
        out.update(s)
        return out
    except Exception:
        return dict(DEFAULT_SETTINGS)


def _save_settings(s):
    os.makedirs(BASE, exist_ok=True)
    json.dump(s, open(SETTINGS_FILE, "w"), indent=1)


app = FastAPI(title="Pocket Voice Studio")


# --- truthful WAV headers ------------------------------------------------
# pocket_tts 2.1.0 writes setnframes(1_000_000_000) as a placeholder and then
# disables wave's header fix-up in finalize(), so every clip it returns claims
# ~11.5 hours. Python's wave module tolerates that on read; ffmpeg duration
# probes, audiobook muxers and media servers do not. Correct it here, at the
# boundary we own, rather than in site-packages where the next pip upgrade
# would silently undo it.
_WAV_PLACEHOLDER = 1_000_000_000


def _fix_wav_header(data: bytes) -> bytes:
    """Return `data` with the RIFF sizes set to the real values.

    Only the size fields change; the PCM payload is left byte-identical.
    Anything that is not a plain RIFF/WAVE blob is returned untouched, so an
    ogg/opus reply (the settings allow ogg for Telegram) passes straight
    through rather than being corrupted.
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data
    raw = bytearray(data)
    pos = 12
    fmt = None
    data_at = None
    while pos + 8 <= len(raw):
        cid = bytes(raw[pos:pos + 4])
        (csize,) = struct.unpack("<I", raw[pos + 4:pos + 8])
        if cid == b"fmt ":
            fmt = bytes(raw[pos + 8:pos + 8 + csize])
        elif cid == b"data":
            data_at = pos
            break
        pos = pos + 8 + csize + (csize & 1)
    if fmt is None or data_at is None or len(fmt) < 16:
        return data
    (declared,) = struct.unpack("<I", raw[data_at + 4:data_at + 8])
    actual = len(raw) - (data_at + 8)
    # nothing to do if the header is already honest
    if declared and declared <= actual:
        return data
    struct.pack_into("<I", raw, 4, 36 + actual)
    struct.pack_into("<I", raw, data_at + 4, actual)
    return bytes(raw)



@app.get("/api/health")
def health():
    ok = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8021/health", timeout=3) as r:
            ok = r.status == 200
    except Exception:
        pass
    return {"studio": True, "pocket_serve": ok}


@app.get("/api/voices")
def list_voices():
    voices = []
    if os.path.isdir(VOICES_DIR):
        for name in sorted(os.listdir(VOICES_DIR)):
            ref = os.path.join(VOICES_DIR, name, "reference.wav")
            if os.path.exists(ref):
                st = os.stat(ref)
                voices.append({"name": name, "size": st.st_size,
                               "added": int(st.st_mtime)})
    return {"voices": voices}


@app.post("/api/voices")
async def add_voice(name: str = Form(...), clip: UploadFile = File(...)):
    name = "".join(c for c in name.strip() if c.isalnum() or c in "-_").lower()
    if not name:
        raise HTTPException(400, "bad name")
    vdir = os.path.join(VOICES_DIR, name)
    os.makedirs(vdir, exist_ok=True)
    raw = os.path.join(vdir, "upload.raw")
    with open(raw, "wb") as f:
        f.write(await clip.read())
    ref = os.path.join(vdir, "reference.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
         "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", ref],
        capture_output=True, timeout=60)
    if r.returncode != 0 or not os.path.exists(ref) or os.path.getsize(ref) < 10000:
        shutil.rmtree(vdir, ignore_errors=True)
        raise HTTPException(400, "ffmpeg conversion failed (clip too short/corrupt?)")
    os.unlink(raw)
    # warm the clone so first real use is fast; also validates the clip works
    warm_ok = False
    try:
        req = _multipart(text="Voice check.", wav_path=ref)
        with urllib.request.urlopen(req, timeout=120) as resp:
            warm_ok = resp.status == 200 and len(resp.read()) > 1000
    except Exception:
        warm_ok = False
    s = _load_settings()
    if s.get("pocket_voice") is None:
        s["pocket_voice"] = name
        _save_settings(s)
    return {"ok": True, "name": name, "clone_validated": warm_ok}


def _multipart(text, wav_path):
    boundary = uuid.uuid4().hex
    b = boundary.encode()
    with open(wav_path, "rb") as f:
        wav = f.read()
    body = b"".join([
        b"--" + b + b"\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\n",
        text.encode() + b"\r\n",
        b"--" + b + (b"\r\nContent-Disposition: form-data; name=\"voice_wav\"; "
                     b"filename=\"ref.wav\"\r\nContent-Type: audio/wav\r\n\r\n"),
        wav + b"\r\n",
        b"--" + b + b"--\r\n",
    ])
    req = urllib.request.Request(
        POCKET_URL, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return req


@app.delete("/api/voices/{name}")
def del_voice(name: str):
    vdir = os.path.join(VOICES_DIR, name)
    if not os.path.isdir(vdir):
        raise HTTPException(404, "no such voice")
    shutil.rmtree(vdir)
    s = _load_settings()
    if s.get("pocket_voice") == name:
        s["pocket_voice"] = None
        rest = [v["name"] for v in (list_voices().get("voices") or [])]
        if rest:
            s["pocket_voice"] = rest[0]
        _save_settings(s)
    return {"ok": True}


@app.post("/api/generate")
def generate(text: str = Form(...), voice: str = Form(None)):
    s = _load_settings()
    voice = voice or s.get("pocket_voice")
    if not voice:
        raise HTTPException(400, "no voice selected")
    ref = os.path.join(VOICES_DIR, voice, "reference.wav")
    if not os.path.exists(ref):
        raise HTTPException(404, f"voice '{voice}' missing reference.wav")
    try:
        with urllib.request.urlopen(_multipart(text=text[:2000], wav_path=ref),
                                    timeout=300) as resp:
            data = resp.read()
    except Exception as exc:
        raise HTTPException(502, f"pocket-tts backend error: {exc}")
    data = _fix_wav_header(data)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(data)
    tmp.close()
    return FileResponse(tmp.name, media_type="audio/wav",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/settings")
def get_settings():
    return _load_settings()


@app.post("/api/settings")
async def set_settings(payload: dict):
    s = _load_settings()
    for k in DEFAULT_SETTINGS:
        if k in payload:
            s[k] = payload[k]
    _save_settings(s)
    return s


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Pocket Voice Studio</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;--acc:#58a6ff;--grn:#3fb950;--red:#f85149}
*{box-sizing:border-box;font-family:ui-sans-serif,system-ui}
body{margin:0;background:var(--bg);color:var(--fg);padding:24px;max-width:900px;margin:auto}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--dim);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.card h2{font-size:14px;margin:0 0 12px;color:var(--acc);text-transform:uppercase;letter-spacing:.5px}
button{background:#21262d;border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:8px 14px;cursor:pointer;font-size:13px}
button:hover{border-color:var(--acc)} button.primary{background:#1f6feb;border-color:#1f6feb}
button.danger{color:var(--red);border-color:var(--red)}
button:disabled{opacity:.45;cursor:not-allowed}
input,select{background:#0d1117;border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:8px;font-size:13px;width:100%}
.row{display:flex;gap:10px;align-items:center}.row>*{flex:1}
#recBtn.recording{background:var(--red);border-color:var(--red);animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.55}}
.status{font-size:12px;color:var(--dim);margin-top:8px;min-height:16px}
.status.ok{color:var(--grn)} .status.err{color:var(--red);font-weight:600}
.voice-item{display:flex;align-items:center;gap:10px;padding:8px;border-bottom:1px solid var(--line)}
.voice-item:last-child{border:none}
.badge{font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid var(--grn);color:var(--grn)}
audio{width:100%;height:36px;margin-top:8px}
label{font-size:12px;color:var(--dim);display:block;margin:10px 0 4px}
</style></head><body>
<h1>🎙️ Pocket Voice Studio</h1>
<div class="sub">Local voice cloning via Kyutai PocketTTS · serves Hermes auto-talk on Telegram/Web-UI</div>

<div class="card">
<h2>1 · Record a voice clip</h2>
<div class="row">
<button id="recBtn" onclick="toggleRec()">● Start Recording</button>
<input id="voiceNameIn" placeholder="new voice-name (letters/digits/-)">
</div>
<label style="margin-top:12px">…or upload an audio file instead (wav/mp3/m4a/ogg/flac — auto-normalized to 24k mono)</label>
<input type="file" id="fileIn" accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac,.webm" onchange="fileChosen(this)">
<audio id="preview" controls style="display:none"></audio>
<div class="row" style="margin-top:10px">
<button id="upBtn" class="primary" onclick="uploadClip()" disabled>⇪ Clone this voice</button>
<span class="status" id="recStatus">Speak for 10–30s: normal pace, quiet room.</span>
</div>
</div>

<div class="card">
<h2>2 · Voice library</h2>
<div id="voiceList">loading…</div>
</div>

<div class="card">
<h2>3 · Try it</h2>
<textarea id="genText" rows="2" style="width:100%;background:#0d1117;border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:8px">Testing my cloned voice on the Orange Pi kernel host.</textarea>
<button class="primary" style="margin-top:8px" onclick="generate()">▶ Generate speech</button>
<audio id="genAudio" controls style="display:none"></audio>
<div class="status" id="genStatus"></div>
</div>

<div class="card">
<h2>4 · Auto-talk settings (Telegram / Web-UI)</h2>
<label>Voice used for auto voice-notes</label>
<select id="setVoice" onchange="saveSetting('pocket_voice',this.value)"></select>
<label>Note length cap (chars)</label>
<input type="number" id="setMax" onchange="saveSetting('max_chars',parseInt(this.value))">
<label><input type="checkbox" id="setEnabled" onchange="saveSetting('voice_notes_enabled',this.checked)" style="width:auto"> Auto voice-notes enabled</label>
<label>Platforms (comma separated)</label>
<input id="setPlatforms" onchange="saveSetting('voice_platforms',this.value.split(',').map(x=>x.trim()))">
<div class="row" style="margin-top:12px">
<button class="primary" onclick="saveAllSettings()">💾 Save settings</button>
<span class="status" id="setStatus"></span>
</div>
</div>

<script>
let mediaRec, chunks=[], clipBlob=null;
const $=id=>document.getElementById(id);
async function api(path,opt){const r=await fetch(path,opt);if(!r.ok){throw new Error((await r.text()).slice(0,200))}return r.json?await r.json():r}

async function refreshVoices(){
  const st=await api('api/settings');curVoice=st.pocket_voice;
  const d=await api('api/voices');const sel=$('setVoice');sel.innerHTML='';
  $('voiceList').innerHTML=d.voices.length?'':'<span class="status">No voices yet — record one above.</span>';
  d.voices.forEach(v=>{
    /* v.name is server-sanitized to [a-z0-9-_] in POST /api/voices before storage */
    const active=(v.name===curVoice);
    const div=document.createElement('div');div.className='voice-item';
    div.innerHTML=`<b>${v.name}</b>${active?'<span class="badge">ACTIVE</span>':''}<span class="status">${(v.size/1024).toFixed(0)} KB</span>
      <button onclick="previewVoice('${v.name}')">▶ sample</button>
      ${active?'':'<button onclick="useVoice(\\''+v.name+'\\')">✓ use</button>'}
      <button class="danger" onclick="delVoice('${v.name}')">delete</button>`;
    $('voiceList').appendChild(div);
    sel.add(new Option(v.name+(active?'  ✅ active':''),v.name));
  });
  if(curVoice)sel.value=curVoice;
  $('setMax').value=st.max_chars;$('setEnabled').checked=st.voice_notes_enabled;
  $('setPlatforms').value=(st.voice_platforms||[]).join(', ');
}
let curVoice=null;
async function toggleRec(){
  if(mediaRec&&mediaRec.state==='recording'){mediaRec.stop();return}
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});
  chunks=[];mediaRec=new MediaRecorder(stream);
  mediaRec.ondataavailable=e=>chunks.push(e.data);
  mediaRec.onstop=()=>{clipBlob=new Blob(chunks,{type:'audio/webm'});
    $('preview').src=URL.createObjectURL(clipBlob);$('preview').style.display='block';
    $('upBtn').disabled=false;$('recBtn').textContent='● Start Recording';$('recBtn').classList.remove('recording');
    stream.getTracks().forEach(t=>t.stop())};
  mediaRec.start();$('recBtn').textContent='■ Stop';$('recBtn').classList.add('recording');
  $('recStatus').textContent='Recording… click stop when done.';
}
async function uploadClip(){
  if(!clipBlob)return;
  const name=($('voiceNameIn').value||('voice-'+Date.now()%10000)).trim();
  $('recStatus').textContent='Cloning… (validates against PocketTTS)';
  const fd=new FormData();fd.append('name',name);fd.append('clip',clipBlob,clipBlob.name||'clip.webm');
  try{const d=await api('api/voices',{method:'POST',body:fd});
    $('recStatus').textContent='✓ Cloned "'+d.name+'"'+(d.clone_validated?' (validated ✓)':' (stored; validation pending backend)');
    $('voiceNameIn').value='';$('fileIn').value='';refreshVoices();
  }catch(e){$('recStatus').textContent='✗ '+e.message}
}
function fileChosen(el){
  const f=el.files[0];if(!f)return;
  clipBlob=f;
  $('preview').src=URL.createObjectURL(f);$('preview').style.display='block';
  $('upBtn').disabled=false;
  $('recStatus').textContent='Loaded '+f.name+' ('+(f.size/1024|0)+' KB) — enter a voice-name and Clone.';
}
async function useVoice(n){await saveSetting('pocket_voice',n);refreshVoices()}
async function delVoice(n){
  if(!confirm('Delete voice "'+n+'"? This removes its reference clip permanently.'))return;
  try{await api('api/voices/'+n,{method:'DELETE'});refreshVoices();}
  catch(e){const el=$('setStatus');el.textContent='✗ delete failed: '+e.message;el.className='status err';}
}
async function saveAllSettings(){
  const body={pocket_voice:$('setVoice').value||null,max_chars:parseInt($('setMax').value)||1200,
    voice_notes_enabled:$('setEnabled').checked,
    voice_platforms:$('setPlatforms').value.split(',').map(x=>x.trim()).filter(Boolean)};
  const el=$('setStatus');
  try{await api('api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    el.textContent='✓ Saved — active voice: '+(body.pocket_voice||'(none)');el.className='status ok';}
  catch(e){el.textContent='✗ Save failed: '+e.message;el.className='status err';}
  setTimeout(()=>{el.textContent='';el.className='status';},4000);
}
async function saveSetting(k,v){
  const body={};body[k]=v;const el=$('setStatus');
  try{await api('api/settings',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(k==='pocket_voice'){el.textContent='✓ Active voice switched to '+v;el.className='status ok';}
    else{el.textContent='Saved ✓';el.className='status ok';}}
  catch(e){el.textContent='✗ Save FAILED: '+e.message;el.className='status err';}
  setTimeout(()=>{el.textContent='';el.className='status';},4000);}
async function previewVoice(n){
  $('genStatus').textContent='Generating sample with '+n+'…';
  const fd=new FormData();fd.append('text','Hi, this is my cloned voice.');fd.append('voice',n);
  const r=await fetch('api/generate',{method:'POST',body:fd});
  const b=await r.blob();$('genAudio').src=URL.createObjectURL(b);$('genAudio').style.display='block';
  $('genStatus').textContent='';
}
async function generate(){previewVoice($('setVoice').value||undefined);
  const fd=new FormData();fd.append('text',$('genText').value);
  if($('setVoice').value)fd.append('voice',$('setVoice').value);
  $('genStatus').textContent='Generating…';
  const r=await fetch('api/generate',{method:'POST',body:fd});
  const b=await r.blob();$('genAudio').src=URL.createObjectURL(b);$('genAudio').style.display='block';
  $('genStatus').textContent='Done.';}
refreshVoices();
</script></body></html>"""


if __name__ == "__main__":
    import os
    uvicorn.run(app, host=os.environ.get("STUDIO_HOST", "0.0.0.0"),
                port=int(os.environ.get("STUDIO_PORT", "8092")), log_level="warning")
