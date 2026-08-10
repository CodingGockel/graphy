# Public access via Cloudflare Tunnel

For a quick public, shareable URL of the running app — e.g. to let others test it —
without port-forwarding, firewall rules, or a static IP, the stack ships an optional
**Cloudflare Tunnel** (`cloudflared`) service.

`cloudflared` makes an **outbound** connection to Cloudflare; Cloudflare then routes
public requests back through that tunnel to the `web` (nginx) container. This bypasses
NAT, router port-forwarding, the host firewall, ISP port blocks, and CGNAT, and gives
you **HTTPS for free** (TLS is terminated by Cloudflare).

```
visitor ──https──▶ <random>.trycloudflare.com ──(Cloudflare)──▶ cloudflared ──▶ web:80 ──▶ backend ──▶ …
                                                                     │  (outbound only)
```

## Prerequisites

- The stack is up (`docker compose up -d`).
- The host is on the **university VPN** — otherwise GraphDB is unreachable and chat
  fails, even though the page loads. See [GraphDB & SPARQL](./graphdb_sparql.md).

## Start the tunnel

The `cloudflared` service is gated behind the `tunnel` Compose **profile**, so it is
**off by default** and only runs when you opt in:

```bash
# 1. Start the tunnel (pulls the cloudflared image on first run)
docker compose --profile tunnel up -d cloudflared

# 2. Grab the public link (give it a few seconds to connect)
docker compose logs cloudflared | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'
```

The printed `https://<random-words>.trycloudflare.com` URL is what you share. Open it in
a browser; visitors can use the app directly.

If the link doesn't appear yet, watch the logs live — it shows up in a boxed
"Your quick Tunnel has been created!" message:

```bash
docker compose logs -f cloudflared
```

## Stop the tunnel (take it offline)

```bash
docker compose stop cloudflared
```

While `cloudflared` runs, the app is public. `stop` takes it offline immediately; the
rest of the stack (localhost) keeps running.

## Important caveats

- **The URL is temporary and random.** With the account-less "Quick Tunnel" it changes
  every time `cloudflared` restarts. For a stable, custom URL you need a Cloudflare
  account + your own domain (a *named tunnel*) — see [Named tunnel](#named-tunnel-stable-url).
- **VPN required.** The tunnel only serves a working app while the host is on the VPN
  (for GraphDB).
- **It spends your LLM key.** Every chat through the link calls the Blablador API with
  your `BLABLADOR_API_KEY`. Only share with people you trust, and `stop` it when done.
- **Your machine must stay awake.** If the host sleeps or WSL/Docker stops, the link
  dies. (No public state is left behind — the URL simply stops resolving.)
- Plain `trycloudflare.com` is best-effort and not meant for production traffic.

## Troubleshooting

### `Failed to dial to edge with quic: timeout: handshake did not complete in time`

`cloudflared` defaults to a **QUIC (UDP, port 7844)** edge connection. Many university
networks and VPNs **block outbound UDP**, so the QUIC handshake times out and the tunnel
never connects.

Fix: force the **HTTP/2 (TCP)** transport instead. This is already configured in
`docker-compose.yml`:

```yaml
command: tunnel --no-autoupdate --protocol http2 --url http://web:80
```

`cloudflared`'s own startup precheck confirms this — it reports
`UDP Connectivity … QUIC connection failed` but `TCP Connectivity … HTTP/2 connection
successful`, with `suggested_protocol=http2`.

### Chat returns 405 / requests go to `/chat` instead of `/api/v1/chat`

A frontend-config issue, not the tunnel — the API base URL lost its `/api/v1` prefix.
Rebuild the `web` image after fixing `frontend/src/lib/api.ts`. (Background: an empty
`VITE_API_BASE_URL` build arg slipping past the `??` fallback.)

### Chat hangs with repeated `307 Temporary Redirect` over the tunnel

Caused by trailing-slash redirects (`/api/v1/chat` → `/api/v1/chat/`) where the backend,
sitting behind nginx, builds the redirect with `http://` while the page is on `https://`
(the tunnel) — the browser blocks it as **mixed content**. Resolved by defining the
routes without a trailing slash and running uvicorn with `--proxy-headers`. If you add
new routes, prefer `@router.post("")` over `@router.post("/")` to avoid reintroducing it.

## Named tunnel (stable URL)

For a permanent URL on your own domain instead of a random `trycloudflare.com` one:

1. Create a Cloudflare account and add your domain.
2. `cloudflared tunnel login`, then `cloudflared tunnel create <name>` to get a
   credentials file and tunnel ID.
3. Run the `cloudflared` container with that tunnel token / credentials (a
   `--token ...` command or a mounted `config.yml`) instead of the `--url` quick-tunnel
   command, and add a DNS route (`cloudflared tunnel route dns <name> app.example.org`).

This is more setup but survives restarts and gives a clean, fixed address. Ask if you
want this wired into the Compose stack.
