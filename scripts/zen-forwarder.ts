
Bun.serve({
  port: 9097,
  async fetch(req) {
    const url = new URL(req.url);
    const target = "https://opencode.ai/zen/v1" + url.pathname.replace(/^\/zenapi/, "");
    const headers = new Headers(req.headers);
    headers.delete("host");
    headers.set("User-Agent", "opencode/1.18.32 ai-sdk/provider-utils/4.0.23 runtime/bun/1.4.2");
    headers.set("x-opencode-client", "cli");
    headers.set("x-opencode-project", "global");
    headers.set("x-opencode-request", "msg_" + crypto.randomUUID().replace(/-/g,"").slice(0,26));
    headers.set("x-opencode-session", "ses_" + crypto.randomUUID().replace(/-/g,"").slice(0,26));
    const body = await req.text();
    const upstream = await fetch(target, { method: req.method, headers, body: body || undefined });
    const text = await upstream.text();
    return new Response(text, { status: upstream.status, headers: {"content-type": upstream.headers.get("content-type") || "application/json"} });
  }
});
console.log("zen forwarder on :9097");
