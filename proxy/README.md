# Local admin reverse proxy

This directory is the local HTTP reverse proxy for the admin origin. It does not serve the storefront, and it does not contain credentials.

The Caddyfile has not been validated and Caddy has not been started from this repository. Validation requires a Caddy binary that is already installed.

## Addresses

| Process | Address | Role |
| --- | --- | --- |
| Caddy | `127.0.0.1:4175` and `[::1]:4175` | Public admin listener |
| Browser origin | `http://admin.localhost:4175` | Host the browser must use |
| FastAPI | `127.0.0.1:4174` | API upstream |
| Next.js | `127.0.0.1:4176` | Admin page upstream |
| Storefront | `127.0.0.1:4173` | Separate process. This proxy never routes to it |

FastAPI and Next.js must stay bound to loopback. Caddy is the only admin listener, and it binds only `127.0.0.1` and `::1`.

## Routes

Requests that reach Caddy with `Host: admin.localhost` are mapped as follows:

- `/api/*` is proxied to `127.0.0.1:4174`.
- Every other path is proxied to `127.0.0.1:4176`.

`Host` and `Origin` are passed through. The Caddyfile does not set `trusted_proxies`. Before forwarding, it removes `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host`. Caddy’s own reverse-proxy behavior then writes those `X-Forwarded-*` fields from the connection it accepted. The client does not choose the upstream scheme.

No CORS headers are added. Cookie names and `Domain` attributes are not rewritten. Nothing is sent to port `4173`.

The storefront keeps using `http://127.0.0.1:4173` on its own. Stopping Caddy does not stop the storefront, and stopping the storefront does not stop this proxy.

## Cookies

`kabaman_session` is a host-only cookie. The admin cookie belongs to `admin.localhost`. The storefront cookie belongs to `127.0.0.1`. Port numbers do not isolate those cookies. Isolation holds only while the hostnames stay different and neither response adds a `Domain` attribute.

## Name resolution

The browser must resolve `admin.localhost` to loopback. Windows does not do that for arbitrary `*.localhost` names through the system resolver. Chromium-based browsers resolve those names themselves. Open `http://admin.localhost:4175` in the browser. Do not add a hosts-file entry as part of this configuration.

Caddy listens on the numeric loopback addresses, so it does not need the system resolver to look up `admin.localhost` before it binds.

## Validate

From the repository root, with a Caddy binary already on `PATH`:

```text
caddy validate --config proxy/Caddyfile --adapter caddyfile
```

This checks the file. It does not start the listener.

## Start and stop

Start FastAPI on `127.0.0.1:4174` and Next.js on `127.0.0.1:4176` yourself. Then, from the repository root:

```text
caddy run --config proxy/Caddyfile --adapter caddyfile
```

Stop Caddy with Ctrl+C in that terminal. `caddy run` stays in the foreground and does not install a service. Do not use `caddy start` unless you also intend to stop that background process with `caddy stop`.

## Secrets

Do not put passwords, tokens, database URLs, or cookie values in the Caddyfile or in this directory.
