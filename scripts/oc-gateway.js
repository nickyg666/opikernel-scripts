
const http = require("http");
const UP = "https://opencode.ai/zen/v1";

function agentShape(body) {
  if (!Array.isArray(body.messages) || body.messages.length === 0) body.messages = [{ role: "user", content: "hi" }];
  if (!body.messages.some(m => m.role === "system")) {
    body.messages.unshift({ role: "system", content: "You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user." });
  }
  if (!Array.isArray(body.tools) || body.tools.length === 0) {
    body.tools = [
      { type: "function", function: { name: "bash", description: "Executes a given bash command in a persistent shell session", parameters: { type: "object", properties: { command: { type: "string", description: "The command to execute" } }, required: ["command"] } } },
      { type: "function", function: { name: "read", description: "Reads a file from the local filesystem", parameters: { type: "object", properties: { path: { type: "string", description: "File path" } }, required: ["path"] } } },
      { type: "function", function: { name: "write", description: "Writes content to a file", parameters: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] } } }
    ];
  }
  if (!body.tool_choice) body.tool_choice = "auto";
  if (body.temperature === undefined) body.temperature = 0.5;
  if (body.reasoning_effort === undefined) body.reasoning_effort = "low";
  body.stream = true;
  if (!body.stream_options) body.stream_options = { include_usage: true };
  if (!body.max_tokens && !body.max_completion_tokens) body.max_tokens = 32000;
  return body;
}

const server = http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString();
  let body;
  try { body = JSON.parse(raw || "{}"); } catch { body = {}; }

  if (req.url.endsWith("/models")) {
    const list = ["ling-3.0-flash-fin-free","mimo-v2.6-flash-free","nemotron-3-ultra-free","nemotron-3.5-lightning-free","deepseek-v4-flash-free","jev-1.13-free","muse-spark-1.2-contributor-free","muse-spark-1.3-contributor-free"];
    const out = JSON.stringify({ object: "list", data: list.map(id => ({ id, object: "model" })) });
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(out);
  }

  body = agentShape(body);
  console.log(new Date().toISOString(), req.url, "model=" + body.model, "temp=" + body.temperature, "effort=" + body.reasoning_effort, "stream=" + body.stream, "tools=" + (body.tools||[]).length, "maxTok=" + body.max_tokens);
  const headers = {
    "content-type": "application/json",
    "user-agent": "opencode/1.18.32 ai-sdk/provider-utils/4.0.23 runtime/bun/1.4.2",
    "x-opencode-client": "cli",
    "x-opencode-project": "global",
    "x-opencode-request": "msg_" + crypto.randomUUID().replace(/-/g, "").slice(0, 26),
    "x-opencode-session": "ses_" + crypto.randomUUID().replace(/-/g, "").slice(0, 26),
    "accept-encoding": "identity"
  };
  if (req.headers["authorization"]) headers["authorization"] = req.headers["authorization"];

  try {
    const out = await fetch(UP + req.url.replace(/^\/zenapi/, "").replace(/^\/v1/, ""), {
      method: "POST", headers, body: JSON.stringify(body)
    });
    res.writeHead(out.status, { "content-type": out.headers.get("content-type") || "application/json", "cache-control": "no-cache" });
    const reader = out.body.getReader();
    (async () => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        res.write(Buffer.from(value));
      }
      res.end();
    })().catch(() => res.end());
    req.on("close", () => { try { reader.cancel(); } catch {} });
  } catch (e) {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: String(e.cause?.code || e.message) } }));
  }
});
server.listen(9099, "127.0.0.1", () => console.log("oc-gateway on 9099"));
