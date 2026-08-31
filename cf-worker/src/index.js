/**
 * LoLCustomRPC anonymous usage stats worker.
 *
 * Endpoints:
 *   POST /install    { client_id, version }  -> counts a new unique install (idempotent)
 *   POST /heartbeat   { client_id, version }  -> marks client as "currently online"
 *   GET  /stats                               -> { online, total_installs }
 *
 * Data stored in KV:
 *   install:<client_id>   = "1"                    (permanent, never expires — used for total_installs count)
 *   online:<client_id>     = "<iso timestamp>"       (TTL ~10 min — used for the "online right now" count)
 *   total_installs         = "<integer>"             (running counter, incremented once per new client_id)
 *
 * No personal data is ever stored — client_id is a random UUID generated
 * locally by the app, with no link to any identity.
 */

const ONLINE_TTL_SECONDS = 10 * 60; // a client counts as "online" for 10 min after its last heartbeat
const HEARTBEAT_LIST_PREFIX = "online:";
const INSTALL_PREFIX = "install:";
const TOTAL_INSTALLS_KEY = "total_installs";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

function isValidClientId(id) {
  // Expect a UUIDv4-shaped string. Reject anything else to keep KV clean.
  return typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
}

async function handleInstall(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: "invalid json" }, 400);
  }

  const clientId = body.client_id;
  if (!isValidClientId(clientId)) {
    return jsonResponse({ error: "invalid client_id" }, 400);
  }

  const installKey = INSTALL_PREFIX + clientId;
  const existing = await env.STATS_KV.get(installKey);

  if (!existing) {
    // First time we've ever seen this client_id — count it once, permanently.
    await env.STATS_KV.put(installKey, "1");
    const current = parseInt((await env.STATS_KV.get(TOTAL_INSTALLS_KEY)) || "0", 10);
    await env.STATS_KV.put(TOTAL_INSTALLS_KEY, String(current + 1));
  }

  return jsonResponse({ ok: true });
}

async function handleHeartbeat(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: "invalid json" }, 400);
  }

  const clientId = body.client_id;
  if (!isValidClientId(clientId)) {
    return jsonResponse({ error: "invalid client_id" }, 400);
  }

  // Mark as online (TTL auto-expires this key — no cleanup job needed).
  await env.STATS_KV.put(HEARTBEAT_LIST_PREFIX + clientId, new Date().toISOString(), {
    expirationTtl: ONLINE_TTL_SECONDS,
  });

  // A heartbeat also counts as an install if we've somehow never seen this
  // client_id before (e.g. the /install call failed on first run).
  const installKey = INSTALL_PREFIX + clientId;
  const existing = await env.STATS_KV.get(installKey);
  if (!existing) {
    await env.STATS_KV.put(installKey, "1");
    const current = parseInt((await env.STATS_KV.get(TOTAL_INSTALLS_KEY)) || "0", 10);
    await env.STATS_KV.put(TOTAL_INSTALLS_KEY, String(current + 1));
  }

  return jsonResponse({ ok: true });
}

async function handleStats(env) {
  let online = 0;
  let cursor;
  do {
    const list = await env.STATS_KV.list({ prefix: HEARTBEAT_LIST_PREFIX, cursor });
    online += list.keys.length;
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);

  const totalInstalls = parseInt((await env.STATS_KV.get(TOTAL_INSTALLS_KEY)) || "0", 10);

  return jsonResponse({ online, total_installs: totalInstalls });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }

    if (request.method === "POST" && url.pathname === "/install") {
      return handleInstall(request, env);
    }
    if (request.method === "POST" && url.pathname === "/heartbeat") {
      return handleHeartbeat(request, env);
    }
    if (request.method === "GET" && url.pathname === "/stats") {
      return handleStats(env);
    }

    return jsonResponse({ error: "not found" }, 404);
  },
};
