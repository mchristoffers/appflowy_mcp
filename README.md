# appflowy_mcp — Homeserver Coolify

A self-owned MCP server for **Moritz's self-hosted AppFlowy Cloud**
(`https://appflowy.mchristoffers.dev`). Oeffentlich erreichbar ueber den
geteilten Homelab-Cloudflare-Tunnel, fuer den claude.ai Web-Connector (der
kann nicht ins Tailnet). Der MCP-Server hat kein eigenes Login — deshalb sitzt
[oauth-agents](https://github.com/mchristoffers/oauth-agents) davor, siehe unten.

Dieses Repo implementiert den MCP-Server selbst (Python/FastMCP), inspiriert
von, aber unabhaengig von den bestehenden `m2n2/appflowy-mcp` /
`weironz/appflowy_mcp`-Projekten. Alle Tools sprechen die native REST-API der
bestehenden AppFlowy-Instanz an.

## Claude Code Plugin

Dieses Repo ist gleichzeitig ein Claude-Code-Plugin (`.claude-plugin/plugin.json`
+ `.mcp.json`) und ein Agent-Plugins-1.0.0-Paket (root `plugin.json` +
`mcp.json`), listet den `appflowy-mcp` MCP-Server via
`https://appflowymcp-oauth.mchristoffers.dev/mcp` (OAuth) und wird ueber die
[mchristoffers/claude-marketplace](https://github.com/mchristoffers/claude-marketplace)
Marketplace installiert. Nichts einzutragen: `oauth-agents` beantwortet
`POST /register` (Dynamic Client Registration) immer mit demselben statischen
Client, und Loopback-Callbacks auf beliebigem Port sind pauschal erlaubt
(RFC 8252).

## Zugriff

**`https://appflowymcp-oauth.mchristoffers.dev/mcp`**

OAuth 2.1 + PKCE, ein Login (`GATEWAY_USERNAME`/`GATEWAY_PASSWORD`). Der
`oauth`-Container ist Authorization Server und Gate in einem: er stellt die
Tokens aus, prueft den Bearer am `/mcp`-Pfad und reicht zum unveraenderten
MCP-Server durch. Er liefert auch die MCP-Protected-Resource-Metadata unter
`/.well-known/oauth-protected-resource`. Hinter dem Tunnel plain HTTP — TLS
terminiert Cloudflare.

## Stack

`docker-compose.production.yml`:

- `appflowymcp` — eigener Build (`Dockerfile`), veroeffentlicht keinen
  Host-Port. Spricht die AppFlowy-REST-API ueber `APPFLOWY_BASE_URL` an und
  haelt die GoTrue-Session selbst (login + refresh).
- `oauth` — `ghcr.io/mchristoffers/oauth-agents`, Port 8085 (nur der
  Tunnel-Container erreicht ihn). Volume `oauth_data:/data` haelt den
  Signing-Key, sonst logged jeder Redeploy alle Clients aus.

Die AppFlowy-Zugangsdaten (`APPFLOWY_EMAIL`/`APPFLOWY_PASSWORD`) + Gateway
(`GATEWAY_USERNAME`/`GATEWAY_PASSWORD`) liegen nur als Coolify-Environment-
Variablen vor, nie in Git.

## Immer aktuell

`image: ghcr.io/mchristoffers/appflowy_mcp:main` plus `pull_policy: always`.
Ein Redeploy zieht damit immer den neuesten Stand. GitHub Actions baut und
pusht das Image nach GHCR, dann loest sie den Coolify-Deploy aus und wartet
auf das Ergebnis. Die Action laeuft zusaetzlich sonntags 04:05 UTC per
`schedule` und aktualisiert von allein.

Kein Rollback vorgesehen; `APPFLOWY_MCP_TAG` existiert trotzdem als
Coolify-Env-Var — im Notfall auf einen `sha-<commit>`-Tag setzen, redeployen.
Kein Backup noetig: der MCP-Server haelt keinen eigenen Datenbestand (nur das
oauth_data-Volume mit dem Signing-Key), er ist jederzeit neu erzeugbar.

## Deploy

Push auf `main` → GitHub Action validiert das Compose, baut+pusht das Image,
signiert das Payload und POSTet es an Coolifys manuellen GitHub-Webhook, dann
wartet sie auf das Ergebnis. Kein Health-Check auf der URL (Endpoint verlangt
jetzt OAuth).

## Lokale Entwicklung

```bash
uv venv && uv pip install -e ".[collab]"
export APPFLOWY_BASE_URL=... APPFLOWY_EMAIL=... APPFLOWY_PASSWORD=...
fastmcp run src/appflowy_mcp/server.py --transport http --port 8001
```
