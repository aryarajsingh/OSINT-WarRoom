# OSINT War Room

> Real-time geopolitical conflict intelligence dashboard — self-hosted, free, runs in one Docker container.

A single screen that tells you what's happening in the world right now, filtered to what actually matters. Tracks geopolitical flashpoints (Iran–Israel, India–China LAC, South China Sea, Taiwan, Russia–NATO, Korea), aggregates from 9 OSINT data sources, classifies and de-duplicates events, and alerts you via Telegram when something escalates.

No accounts to manage, no subscriptions, no telemetry. Every data source is free. The entire stack runs in one container with no external services and no cloud.

---

## Features

- **9 data sources**: RSS (73 feeds), GDELT Doc 2.0, GDELT Geo, ACLED, NASA FIRMS, USGS, ADS-B (military aircraft), UCDP, public Telegram OSINT channels.
- **Smart classification**: every event is tagged by region (5), flashpoint (6), priority (0–100), source tier, and Goldstein scale estimate.
- **Two-phase deduplication**: exact-match hash dedup plus Jaccard similarity to suppress repeated coverage of the same event across sources.
- **5-panel dashboard**: Live map (Leaflet), Breaking Feed, India Command, Great Powers tracker, Situation Board (flashpoint escalation table). Drag-resizable panels, dark theme.
- **Real-time updates**: Server-Sent Events stream new events to the browser as they arrive.
- **Telegram alerts**: critical/high-priority events hit your phone within seconds, with batching and boot-time suppression.
- **Full-text search**: SQLite FTS5 index across every event ever ingested.

---

## Tech stack

Python 3.12 · FastAPI · HTMX · SSE · SQLite (FTS5, WAL mode) · Leaflet · APScheduler · Docker

No frontend build step. No npm. No Node. Templates are Jinja2; JS is vanilla plus HTMX.

---

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/aryarajsingh/OSINT-WarRoom.git
cd OSINT-WarRoom
cp .env.example .env
# fill in the 4 secrets in .env (see "Configuration" below)
docker compose up -d --build
```

Open <http://localhost:8000>.

### macOS (double-click)

```bash
bash setup_mac.command       # one-time
```

Then double-click `start_mac.command`. Stop with `stop_mac.command`.

### Windows (double-click)

Double-click `start.bat`. Stop with `stop.bat`.

---

## Configuration

Copy `.env.example` to `.env` and fill in the four secrets:

| Variable | Where to get it |
|----------|-----------------|
| `TELEGRAM_BOT_TOKEN` | Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, copy the token |
| `TELEGRAM_CHAT_ID` | Message [@userinfobot](https://t.me/userinfobot) on Telegram |
| `ACLED_EMAIL` / `ACLED_PASSWORD` | Free registration at [acleddata.com](https://acleddata.com) (OAuth2, no separate API key) |
| `FIRMS_MAP_KEY` | Free registration at [earthdata.nasa.gov](https://earthdata.nasa.gov) → FIRMS Map Key |

Optional knobs in `.env`:

- `GOLDSTEIN_CRITICAL`, `GOLDSTEIN_HIGH`, `GOLDSTEIN_MEDIUM` — alert priority thresholds
- `RETENTION_DAYS` — how long to keep events (default 90)
- `HTTP_PROXY` / `HTTPS_PROXY` — route all outbound traffic through a proxy or VPN

`.env` is gitignored. Never commit it.

RSS feed sources live in `data/feeds.yml` and can be edited freely.

---

## Sharing the dashboard externally

Run `share_mac.command` (or `share.bat`) to spin up a Cloudflare tunnel and get a public HTTPS URL. Useful for showing the dashboard to someone or accessing it from your phone without exposing ports.

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design — directory layout, data flow, schema, dedup logic, classifier rules, alert engine, panel-by-panel UI breakdown.

---

## Disclaimer

Built as a personal situational-awareness tool using only public OSINT data. Not an authoritative intelligence source. Treat events as leads, not facts — verify before acting on anything important.

---

## License

[MIT](LICENSE) © 2026 Aryaraj Singh
