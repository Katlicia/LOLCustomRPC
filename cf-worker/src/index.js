/**
 * LoLCustomRPC anonymous usage stats worker.
 *
 * Endpoints:
 *   POST /install    { client_id, version }  -> counts a new unique install (idempotent)
 *   POST /heartbeat   { client_id, version }  -> marks client as "currently online"
 *   GET  /stats                               -> { online, total_installs }
 *
 * Data stored in KV (installs — permanent, get/put only, no list() calls):
 *   install:<client_id>   = "1"        (permanent — used for total_installs count)
 *   total_installs         = "<integer>" (running counter, incremented once per new client_id)
 *
 * "Online right now" is tracked separately in a single ONLINE_COUNTER
 * Durable Object instance (see the OnlineCounter class below), which keeps
 * an in-memory map of client_id -> last-seen timestamp. This avoids
 * Workers KV's list() operation entirely — KV's free tier caps list() at
 * 1000/day, and a live "online count" polled every 60s by every open
 * Settings window would blow through that almost immediately (each /stats
 * call used to cost one list() call). Durable Object storage has no such
 * per-operation list quota.
 *
 * No personal data is ever stored — client_id is a random UUID generated
 * locally by the app, with no link to any identity.
 */

const ONLINE_TTL_MS = 10 * 60 * 1000; // a client counts as "online" for 10 min after its last heartbeat
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
  // Expect a UUIDv4-shaped string. Reject anything else to keep storage clean.
  return typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
}

/**
 * Durable Object holding the "who's online right now" state in memory,
 * backed by its own storage (not KV) so it survives a cold restart.
 * Only one instance of this ever exists (see idFromName("global") below),
 * so all heartbeats/reads go through the same in-memory map — no list()
 * scans, no per-key KV reads.
 */
export class OnlineCounter {
  constructor(state) {
    this.state = state;
    // clientId -> last-seen epoch ms. Loaded lazily from storage on first use.
    this.online = null;
  }

  async _ensureLoaded() {
    if (this.online) return;
    const stored = await this.state.storage.get("online");
    this.online = stored instanceof Map ? stored : new Map();
  }

  async _persist() {
    // Durable Object storage handles Maps natively via structured clone.
    await this.state.storage.put("online", this.online);
  }

  async fetch(request) {
    await this._ensureLoaded();
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/mark-online") {
      const { client_id: clientId } = await request.json();
      this.online.set(clientId, Date.now());
      await this._persist();
      return jsonResponse({ ok: true });
    }

    if (request.method === "GET" && url.pathname === "/count") {
      const now = Date.now();
      let count = 0;
      let changed = false;
      for (const [id, lastSeen] of this.online) {
        if (now - lastSeen > ONLINE_TTL_MS) {
          this.online.delete(id);
          changed = true;
        } else {
          count++;
        }
      }
      if (changed) await this._persist();
      return jsonResponse({ online: count });
    }

    return jsonResponse({ error: "not found" }, 404);
  }
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

  // Mark as online via the Durable Object (in-memory, no KV list() involved).
  const counterId = env.ONLINE_COUNTER.idFromName("global");
  const counter = env.ONLINE_COUNTER.get(counterId);
  await counter.fetch("https://counter/mark-online", {
    method: "POST",
    body: JSON.stringify({ client_id: clientId }),
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
  const counterId = env.ONLINE_COUNTER.idFromName("global");
  const counter = env.ONLINE_COUNTER.get(counterId);
  const countResp = await counter.fetch("https://counter/count");
  const { online } = await countResp.json();

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
