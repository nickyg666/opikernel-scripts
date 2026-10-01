#!/usr/bin/env python3
"""Inject the Pocket Voice Studio launcher into the Hermes Web UI client page.

Idempotent + self-updating: strips any previously injected block between
PVS-BEGIN/PVS-END markers, then installs the current version.
Re-run after any `npm i -g hermes-web-ui` update wipes dist/client/index.html.
"""
import re
import sys

PAGE = "/usr/local/lib/node_modules/hermes-web-ui/dist/client/index.html"

# Origin-gated launcher: only renders on the Caddy-mounted origin where
# /voice-studio/ actually IS the studio (JSON health). The studio service is
# loopback-only, so there is deliberately no :8092 fallback — access is
# exclusively via the Hermes Web UI HTTPS address.
JS = """
<!-- PVS-BEGIN Pocket Voice Studio launcher (~/opikernel/services/webui_voice_launcher.py) -->
<script>
(function(){
  function add(probe){
    if(document.getElementById('pvs-launcher'))return;
    if(!probe || (probe.headers.get('content-type')||'').indexOf('json')<0)return;
    var a=document.createElement('a');
    a.id='pvs-launcher';
    a.href='/voice-studio/';
    a.title='Pocket Voice Studio - record/upload voice clips, clone and generate speech (100% local)';
    a.textContent='\\uD83C\\uDFA4 Voice Studio';
    a.style.cssText='position:fixed;right:14px;bottom:39px;z-index:2147483000;display:inline-flex;align-items:center;padding:8px 14px;border-radius:999px;background:#1f6feb;color:#fff;font:600 12.5px/1 system-ui,sans-serif;text-decoration:none;box-shadow:0 2px 10px rgba(0,0,0,.35);opacity:.9;cursor:pointer';
    document.body.appendChild(a);
  }
  fetch('/voice-studio/api/health',{cache:'no-store'})
    .then(function(r){add(r.ok?r:null);})
    .catch(function(){});
})();
</script>
<!-- PVS-END -->
"""


def main():
    s = open(PAGE, encoding="utf-8").read()
    n = len(s)
    s = re.sub(r"\n?<!-- PVS-BEGIN.*?PVS-END -->\n?", "\n", s, flags=re.S)
    # strip legacy (pre-marker) v1 launcher block
    s = re.sub(
        r"\n?<script>\n/\* Pocket Voice Studio launcher \(installed by"
        r" ~/opikernel/services/webui_voice_launcher\.sh\) \*/.*?</script>\n?",
        "\n", s, flags=re.S)
    changed = len(s) != n
    assert s.rstrip().endswith("</html>"), "unexpected index.html tail"
    if "</body>" in s:
        s = s.replace("</body>", JS + "</body>")
    else:
        s = s.rstrip()[: -len("</html>")] + JS + "</html>"
    open(PAGE, "w", encoding="utf-8").write(s)
    print("reinstalled" if changed else "installed")


if __name__ == "__main__":
    sys.exit(main())
