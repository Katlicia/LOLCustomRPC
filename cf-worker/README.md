# lolcustomrpc-stats

Cloudflare Worker that powers anonymous usage stats for LoLCustomRPC:
- `POST /install` — counts a unique installation (idempotent by client_id)
- `POST /heartbeat` — marks a client as "online right now" (10 min TTL)
- `GET /stats` — returns `{ online, total_installs }`

No personal data is stored. `client_id` is a random UUIDv4 generated locally
by the app on first run — it identifies a device, not a person.

## First-time setup

1. Install dependencies:
   ```
   cd cf-worker
   npm install
   ```

2. Log in to your Cloudflare account (opens a browser):
   ```
   npx wrangler login
   ```

3. Create the KV namespace:
   ```
   npx wrangler kv namespace create STATS_KV
   ```
   This prints an `id`. Copy it into `wrangler.toml`, replacing
   `REPLACE_WITH_KV_NAMESPACE_ID`.

4. Deploy:
   ```
   npm run deploy
   ```
   Wrangler prints the live URL. Live at:
   `https://lolcustomrpc-stats.katlicia.workers.dev`

5. Put that URL into the app's `services/stats.py` (`STATS_API_BASE`).
   Already set for this deployment.

## Local dev

```
npm run dev
```
Runs the worker locally with a local KV emulation for testing.

## Redeploying after changes

```
npm run deploy
```
The live URL stays the same across redeploys.
