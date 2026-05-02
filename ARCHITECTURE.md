# OSINT War Room — Complete Architecture

## Intent

A passion project built for personal use. The goal: a single screen that tells me what's happening in the world right now — filtered to what actually matters, laid out the way I want it, updating in real time without me having to check ten different sites and channels.

I track geopolitical flashpoints (Iran-Israel, India-China LAC, South China Sea, Taiwan, Russia-NATO, Korea) and want to know immediately when something escalates — not buried in a news feed alongside celebrity gossip. The dashboard is tuned to my interests: India defence gets its own command panel, great power moves are tracked separately, and the situation board gives me a single glance at which flashpoints are heating up.

Everything is free, self-hosted, and runs in a single Docker container. No accounts to manage, no subscriptions, no telemetry. Just `docker compose up` and open localhost.

## Project Overview

A real-time geopolitical conflict intelligence aggregation platform. Collects from 9 data sources (including GDELT Geo), classifies by region/priority/flashpoint, stores in SQLite with FTS5 search, alerts via Telegram bot, and displays on a 5-panel dark-themed dashboard with SSE live updates and drag-resizable panels.

**Stack**: Python 3.12 · FastAPI · HTMX · SSE · SQLite (FTS5) · Leaflet · Docker

### Design Principles
- **Relevance over volume** — Aggressive filtering and classification so noise never reaches the dashboard. Relevance gates, keyword scoring, and dedup ensure only meaningful intel surfaces.
- **Glanceable** — The 5-panel layout is designed so that a single look tells you what's happening, where, and how serious it is. No clicking through menus.
- **Real-time** — SSE pushes events to the browser as they arrive. Telegram alerts hit your phone for critical/high priority events within seconds.
- **Zero cost, zero dependency** — Every data source is free. The entire stack runs in one container with no external services, no cloud, no build tools.
- **Tuned to my perspective** — India Command exists because I care about Indian defence. Africa is a region because those conflicts matter. The priority scoring rewards action over analysis because I want to know when things happen, not when someone writes about them.

---

## Directory Structure

```
osint-warroom/
├── .env                             # Credentials & thresholds
├── .env.example                     # Template
├── Dockerfile                       # Python 3.12-slim, uvicorn
├── docker-compose.yml               # Single service, port 8000
├── requirements.txt                 # FastAPI, httpx, aiosqlite, apscheduler
├── start.bat / stop.bat / share.bat  # Windows (double-click)
├── setup_mac.command                 # Mac one-time setup (run first)
├── start_mac.command                 # Mac start (double-click)
├── stop_mac.command                  # Mac stop (double-click)
├── share_mac.command                 # Mac share anywhere (double-click)
├── ARCHITECTURE.md                  # This file
│
├── app/
│   ├── main.py                      # FastAPI app, lifespan, scheduler
│   ├── config.py                    # Settings, flashpoints, region maps, keywords
│   ├── models.py                    # Pydantic schemas (Event, Flashpoint)
│   ├── database.py                  # aiosqlite, FTS5, CRUD, queries, dedup
│   │
│   ├── collectors/                  # 9 data source collectors
│   │   ├── rss.py                   # RSS/Atom feeds (73 feeds)
│   │   ├── gdelt.py                 # GDELT Doc 2.0 API (text articles)
│   │   ├── gdelt_geo.py             # GDELT Doc 2.0 PointData (geocoded map events)
│   │   ├── acled.py                 # ACLED conflict events (OAuth2)
│   │   ├── firms.py                 # NASA FIRMS thermal anomalies
│   │   ├── usgs.py                  # USGS seismic (M4.5+)
│   │   ├── adsb.py                  # Military aircraft tracking
│   │   ├── ucdp.py                  # Uppsala conflict dataset (CSV)
│   │   └── telegram_channels.py     # Public OSINT Telegram channels (15 channels)
│   │
│   ├── processing/                  # Classification & scoring
│   │   ├── classifier.py            # Region, priority, flashpoint, tier, Goldstein estimation
│   │   ├── dedup.py                 # Jaccard similarity deduplication (stop word aware)
│   │   └── situation.py             # Flashpoint escalation scoring
│   │
│   ├── alerts/                      # Notification engine
│   │   ├── engine.py                # Batching, SSE broadcast, routing, boot suppression
│   │   └── telegram.py              # Telegram Bot API wrapper + alert formatter
│   │
│   ├── routes/                      # HTTP endpoints & SSE
│   │   ├── dashboard.py             # GET / (main page)
│   │   ├── partials.py              # HTMX partial endpoints
│   │   ├── sse.py                   # Server-Sent Events streams
│   │   └── api.py                   # JSON API (geojson, search, flashpoints)
│   │
│   ├── static/                      # Frontend assets
│   │   ├── dashboard.js             # Map, filters, SSE, keyboard shortcuts, drag resize
│   │   ├── style.css                # Dark theme CSS
│   │   ├── htmx.min.js             # HTMX library
│   │   ├── htmx-sse.js             # SSE extension
│   │   ├── leaflet.min.js/css      # Leaflet maps
│   │   ├── sparkline.js            # Sparkline charts
│   │   └── alert.mp3               # Notification sound
│   │
│   └── templates/                   # Jinja2 templates
│       ├── base.html                # Layout shell, security headers
│       ├── index.html               # 5-panel dashboard grid
│       └── partials/
│           ├── event_card.html      # Single event card
│           ├── feed_panel.html      # Event list wrapper
│           ├── india_panel.html     # India Command panel
│           ├── powers_panel.html    # Great Power tracker
│           └── situation_panel.html # Flashpoint table
│
└── data/
    ├── feeds.yml                    # RSS feed configuration (73 feeds)
    └── warroom.db                   # SQLite database (WAL mode)
```

---

## Data Flow

```
COLLECTION            PROCESSING               STORAGE            DISPLAY
──────────            ──────────               ───────            ───────

RSS (73 feeds) ──┐
GDELT (8 queries)┤
GDELT Geo (6 q.) ┤
ACLED (OAuth2) ──┤   classify_event()          events table       Dashboard
FIRMS (5 zones) ─┤   ┌─ region (5 regions)     ├─ FTS5 index      ├─ Map panel
USGS (M4.5+) ───┤   ├─ flashpoint (6 zones)   ├─ Indexes         ├─ Breaking Feed
ADS-B (military)─┤   ├─ priority (scored 0-100) │                  ├─ India Command
UCDP (CSV) ─────┤   ├─ source_tier            │                  ├─ Great Powers
Telegram (15 ch) ┘   ├─ goldstein (estimated)  │                  └─ Situation Board
                      ├─ india category         │
                      └─ dedup_hash             │
                                                │
                      insert_event() ───────────┘
                          │
                          ├─→ Phase 1: Exact dedup (MD5 hash, 6-hour window)
                          ├─→ Phase 2: Cross-source fuzzy dedup (Jaccard, 0.55 threshold)
                          │
                          ├─→ Alert Engine
                          │    ├─ CRITICAL → Instant Telegram + photo + location
                          │    ├─ HIGH     → 1-min batch Telegram (max 10 per batch)
                          │    └─ MEDIUM/LOW → Dashboard only
                          │
                          ├─→ SSE Broadcast
                          │    ├─ /sse/feed   → Live event cards
                          │    └─ /sse/alerts → Critical alert banners
                          │
                          └─→ Flashpoint Scorer
                               → Score 0-100 → Status (BASELINE to CRITICAL)
```

---

## Collectors

| Source | Interval | API / Method | Data Type | Has Lat/Lon | Notes |
|--------|----------|-------------|-----------|-------------|-------|
| **RSS** | Hot: 2m, Warm: 10m | feedparser | News articles | No | 73 feeds across 10 categories |
| **GDELT** | 15 min | HTTP JSON | Conflict articles | No | 8 keyword queries, 1s delay between |
| **GDELT Geo** | 30 min | HTTP JSON (PointData) | Geocoded news clusters | Yes | 6 conflict queries, map-only events |
| **ACLED** | 60 min | OAuth2 REST | Conflict events | Yes | 7-day window, fatalities, actor data |
| **FIRMS** | 60 min | CSV download | Thermal anomalies | Yes | 5 zones, high confidence or FRP>10MW |
| **USGS** | 30 min | GeoJSON | Earthquakes M4.5+ | Yes | 50 latest events |
| **ADS-B** | 5 min | JSON (3 fallback APIs) | Military aircraft | Yes | 23 recognized types, ISR/bombers/fighters |
| **UCDP** | 6 hours | CSV download | Historical conflicts | Yes | 90-day window, capped at priority 40 |
| **Telegram** | 2 min | Web scrape (t.me/s/) | OSINT channel posts | No | 15 channels, 10 msgs each, relevance gated |

### RSS Feed Categories (feeds.yml)
- **Wire Services** (hot): Al Jazeera, BBC World, Times of Israel
- **India Government**: PIB Defence, PIB All
- **India Defence Media**: Indian Express, NDTV, Livefist, Bharat Shakti
- **India Think Tanks**: IDSA, Carnegie India
- **US Defence**: DefenseOne, Breaking Defense, War on the Rocks, USNI, Military Times, The War Zone
- **China Watch**: SCMP, Jamestown, The Diplomat
- **Middle East**: Al-Monitor, Middle East Eye, BBC ME
- **Geopolitics**: Foreign Affairs, CSIS, RAND
- **Travel Advisories**: UK FCDO, Australia DFAT
- **Europe/Russia-Ukraine**: ISW, BBC Europe

### Telegram Channels (15)

| Region | Channels |
|--------|----------|
| **Global / Multi-region** | Aurora Intel, BNO News, OSINTdefender, Conflict Intelligence, Intel Republic, War Monitors, Military Brief |
| **Europe / Russia-Ukraine** | Liveuamap, Flash News, NEXTA Live, The Dead District |
| **Middle East** | Middle East Spectator, MENA Updates |
| **Asia-Pacific** | SCS Probing Initiative |
| **India** | India Defence News |

### Telegram Relevance Gate
Messages are pre-filtered at collection time using a `RELEVANCE_SIGNALS` frozenset (~70 conflict/geopolitical terms). Messages with zero signal word matches are discarded before classification. This prevents irrelevant content (memes, ads, off-topic chatter) from entering the pipeline.

---

## Deduplication (Two-Phase)

### Phase 1: Exact Dedup
- MD5 hash of `lowercase(title) + "|" + source`
- 6-hour dedup window per hash
- Same-source, same-headline protection

### Phase 2: Cross-Source Fuzzy Dedup
- Runs on `insert_event()` for titles > 20 chars
- Queries last 200 titles from the past 3 hours
- Jaccard similarity with stop word removal (~30 common words including "breaking", "update", "says", "via")
- Threshold: 0.55 (rejects near-duplicate headlines across different sources)
- Example: "BREAKING: IDF strikes southern Lebanon" from Aurora Intel won't duplicate the same story from BNO News

---

## Priority Scoring System (0-100)

### Components

| Component | Weight | Signals |
|-----------|--------|---------|
| **Source Weight** | 0-25 | Telegram OSINT: 22, Wire: 20, ACLED: 18, Gov: 12, UCDP: 10, FIRMS: 8, Analysis: 3 |
| **Action Signals** | 0-40 | 35 keywords. Strong (3+ hits): 40. Moderate (2): 30. Weak (1): 18 |
| **Escalation Signals** | 0-25 | 27 keywords. Double (2+): 25. Single: 12 |
| **Development Signals** | 0-8 | 10 keywords. Only fires when action_hits == 0 |
| **Severity** | 0-20 | Goldstein ≤-8: 20, ≤-5: 12, ≤-3: 5. Fatalities ≥50: 25, ≥10: 15, >0: 8 |
| **Context Boost** | 0-15 | India region + keywords: 8-15. Active flashpoint: 5. FIRMS in flashpoint: 12 |
| **Dampeners** | 0 to -20 | 18 dampener words (uses word-boundary matching). Heavy (3+): -20. Moderate (2): -12. Light (1): -5. USGS: -15. UCDP capped at 40. FIRMS without flashpoint: -10 |

### Action Keywords (35)
`strikes, struck, attacked, launched, shelling, explosion, blast, detonation, intercept, killed, casualties, death toll, invaded, incursion, breached, shot down, downed, sunk, breaking, just in, developing, happening now, confirmed dead, reports of, underway, fired upon, missile launch, rocket attack, air raid, bombardment, carpet bomb, declared war, martial law, state of emergency, ceasefire violated, ceasefire collapsed, ambush, raid, hostage, kidnapped, abducted, siege, assassination, assassinated, coup, overthrown, hijacked, targeted killing, neutralized, stormed, overrun, captured, car bomb, suicide bomb, ied, mass shooting, massacre`

### Escalation Keywords (27)
`deployed, mobilized, buildup, amassing, carrier strike group, naval blockade, no-fly zone, nuclear test, icbm, thermonuclear, border standoff, troops massed, evacuate embassy, recalled ambassador, ultimatum, threatens retaliation, chemical weapon, biological weapon, article 5, mutual defense, war footing, conscription, general mobilization, defcon, nuclear alert, red line crossed, nuclear posture, strategic deterrent, full mobilization, war declaration, emergency session, un security council`

### Dampener Keywords (18)
`report, analysis, commentary, opinion, editorial, perspective, assessment, outlook, review, could, should, may impact, might lead, history of, looking back, lessons from, plans to, budget, challenges for, fleet size, upgrade plans, modernization, why it matters, how it works, what it means, q&a, interview, podcast, webinar, explainer, backgrounder, timeline of`

### Keyword Matching
All keyword matching uses word-boundary regex (`\bkeyword\b`) to prevent false positives. This means "report" won't match inside "reported", "fleet" won't match inside "reflection", etc.

### Goldstein Estimation
Events without a Goldstein score (RSS, Telegram) get one estimated from keyword signals:
- 3+ action hits → -9.0
- 2 action hits → -7.0
- 1 action + 1 escalation → -6.0
- 1 action → -4.0
- 2+ escalation → -5.0
- 1 escalation → -3.0
- 3+ dampener → +1.5
- No strong signals → None (unscored)

### Thresholds

| Priority | Score | Alert Action |
|----------|-------|-------------|
| **CRITICAL** | ≥70 | Instant Telegram (photo + location + sound) |
| **HIGH** | ≥45 | 1-min batched Telegram (max 10 per batch) |
| **MEDIUM** | ≥25 | Dashboard + SSE only |
| **LOW** | <25 | Dashboard + SSE only |

---

## Flashpoint Escalation Scoring

### 6 Monitored Flashpoints

| Flashpoint | Center | Radius | Keywords (count) |
|-----------|--------|--------|------------------|
| **Iran-Israel-US** | 32.0°N, 48.0°E | 2000km | 38 keywords: iran, israel, hezbollah, houthi, hamas, tehran, idf, irgc, khamenei, netanyahu, nasrallah, quds force, centcom, al-asad, negev, natanz, dimona, golan, west bank, rafah, gaza, beirut, dahieh, arak, parchin, isfahan, bandar abbas, red sea, hormuz, strait of hormuz, gulf of oman, bab el-mandeb, iron dome, david's sling, arrow missile, shahed, fateh |
| **India-China LAC** | 33.5°N, 78.5°E | 800km | 19 keywords: lac, line of actual control, pangong, galwan, doklam, tawang, arunachal, ladakh, aksai chin, depsang, hot springs, gogra, demchok, chushul, eastern ladakh, itbp, border roads, china border, sino-indian border |
| **South China Sea** | 12.0°N, 114.0°E | 1500km | 22 keywords: south china sea, spratlys, scarborough, scarborough shoal, second thomas, second thomas shoal, fiery cross, mischief reef, ccg, philippine, ayungin, sierra madre, whitsun reef, paracel, reed bank, nine dash, nine-dash line, subi reef, woody island, philippine coast guard, china coast guard, sulu sea |
| **Taiwan Strait** | 24.0°N, 120.0°E | 500km | 12 keywords: taiwan, taipei, pla, taiwan strait, median line, kinmen, matsu, lai ching-te, william lai, adiz, taiwan adiz, tsai ing-wen, kaohsiung, hualien, eastern theater command |
| **Russia-NATO** | 50.0°N, 35.0°E | 2000km | 28 keywords: ukraine, russia, nato, crimea, donbas, kherson, zaporizhzhia, kursk, black sea fleet, belgorod, sumy, kaliningrad, bakhmut, avdiivka, pokrovsk, tokmak, himars, patriot, leopard, abrams, challenger, storm shadow, scalp, atacms, gepard, lancet, iskander, kinzhal, ramstein, kyiv, zelensky, putin, wagner, akhmat |
| **Korea** | 38.0°N, 127.0°E | 500km | 15 keywords: north korea, dprk, pyongyang, kim jong, dmz, icbm, hwasong, yongbyon, punggye-ri, kaesong, panmunjom, musudan, unha, usfk, nll, northern limit line |

### Score Formula (0-100)

```
score = frequency(35%) + severity(25%) + thermal(20%) + diversity(10%) + fatalities(10%)

frequency  = (events_24h / 10) * 100
severity   = max(0, (-avg_goldstein / 10) * 100)
thermal    = firms_count * 25
diversity  = distinct_sources * 15
fatalities = (total_fatalities / 50) * 100
```

### Status Mapping

| Score | Status | Color |
|-------|--------|-------|
| ≥81 | CRITICAL | Red, pulsing |
| 61-80 | ESCALATING | Orange |
| 41-60 | ELEVATED | Yellow |
| 21-40 | STABLE | Green |
| <21 | BASELINE | Gray |

---

## Region Classification

### 5 Regions

| Region | Keyword Count | Key Terms |
|--------|--------------|-----------|
| **india** | 19 | indian navy, indian air force, indian army, modi, drdo, isro, tejas, brahmos, ladakh, kashmir, ins arihant, barc, hal tejas |
| **middle_east** | 27 | iran, israel, gaza, hamas, hezbollah, houthi, yemen, idf, irgc, red sea, strait of hormuz, bab el-mandeb, al-aqsa |
| **asia_pacific** | 18 | china, taiwan, pla, south china sea, japan, korea, dprk, asean, aukus, xi jinping, senkaku, first island chain |
| **europe** | 17 | ukraine, russia, nato, crimea, baltic, wagner, putin, zelensky, donbas, article 5, kaliningrad, ramstein |
| **africa** | 19 | sudan, khartoum, rsf, darfur, ethiopia, tigray, somalia, al-shabaab, drc, m23, sahel, mali, burkina faso, boko haram, african union, ecowas |

### COUNTRY_REGION_MAP (config.py)
Maps 55+ countries to 5 regions:
- **india**: India (strict — only India itself)
- **south_asia**: Pakistan, Nepal, Sri Lanka, Bangladesh, Maldives (not routed to India Command)
- **asia_pacific**: China, Myanmar, Philippines, Japan, South Korea, North Korea, Taiwan, Vietnam, Thailand, Indonesia, Malaysia, Cambodia, Laos, Australia
- **middle_east**: Israel, Iran, Iraq, Syria, Yemen, Lebanon, Saudi Arabia, Palestine, Turkey, Jordan, UAE, Oman, Qatar, Bahrain, Kuwait, Egypt, Libya
- **europe**: Ukraine, Russia, Belarus, Poland, Romania, Moldova, Georgia, Armenia, Azerbaijan
- **africa**: Sudan, South Sudan, Ethiopia, Somalia, DR Congo, Mali, Burkina Faso, Niger, Nigeria, Chad, Mozambique, Central African Republic, Cameroon

### REGION_BOUNDS (for map auto-zoom)
- india: `[[6, 68], [37, 98]]`
- middle_east: `[[12, 25], [42, 65]]`
- asia_pacific: `[[0, 95], [50, 150]]`
- europe: `[[35, -10], [72, 60]]`
- africa: `[[-35, -20], [38, 55]]`

---

## India Command — Category Classification

India events are categorized into 6 categories using keyword-based classification:

| Category | Tab | Keywords (sample) |
|----------|-----|-------------------|
| **lac** | LAC | lac, pangong, galwan, doklam, china border, itbp, border clash |
| **procurement** | Defence | drdo, brahmos, tejas, rafale, hal, bel, s-400, aircraft carrier, dac |
| **diplomacy** | Diplomacy | jaishankar, bilateral, g20, quad, brics, mea, indo-pacific, treaty |
| **analysis** | (filtered to All) | idsa, carnegie india, commentary, policy brief, strategic assessment |
| **space** | Space | isro, pslv, gslv, chandrayaan, gaganyaan, sriharikota, asat |
| **nuclear** | Nuclear | barc, ins arihant, agni missile, nuclear triad, k-4 missile, slbm |
| **defence** | Defence | Default fallback if no other category matches |

### India Relevance Gate
- **Trusted sources** (PIB, Livefist, Bharat Shakti, IDSA, Carnegie India, etc.): Must match ≥1 India relevance keyword
- **General sources**: Must match ≥2 India relevance keywords
- Events failing the gate have their `region` and `category` cleared (appear in global feed only)
- This prevents non-India content from leaking into India Command even from Indian sources

---

## Source Tier Classification

| Tier | Sources |
|------|---------|
| **WIRE** | reuters, associated press, al jazeera, bbc, ndtv, times of israel, scmp, military times, usni, janes, xinhua, tass, yonhap |
| **GOV** | pib, mea, mod.gov, drdo, state.gov, defense.gov, indiannavy, fcdo, ucdp |
| **OSINT** | aurora intel, osintdefender, bno, liveuamap, conflict intelligence, nexta, the dead district, flash news, the war zone, breaking defense, defense one, intel republic, middle east spectator, scs probing, india defence news |
| **ANALYSIS** | orf, idsa, csis, rand, carnegie, war on the rocks, iiss, rusi, brookings, foreign affairs, the diplomat, bharat shakti, livefist, jamestown |
| **Fallback by source_type** | telegram→OSINT, gdelt/gdelt_geo→WIRE, ucdp/acled/firms/usgs→GOV, adsb→OSINT |

---

## Database Schema

### Main Table: `events`

```sql
CREATE TABLE events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    summary         TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    source          TEXT DEFAULT '',
    source_type     TEXT DEFAULT 'rss',
    source_tier     TEXT DEFAULT 'UNKNOWN',
    region          TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    priority        TEXT DEFAULT 'low',
    goldstein       REAL,
    lat             REAL,
    lon             REAL,
    image_url       TEXT DEFAULT '',
    fatalities      INTEGER DEFAULT 0,
    flashpoint      TEXT DEFAULT '',
    is_read         INTEGER DEFAULT 0,
    is_pinned       INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now')),
    dedup_hash      TEXT DEFAULT ''
);
```

### FTS5 Virtual Table

```sql
CREATE VIRTUAL TABLE events_fts USING fts5(
    title, summary, source, region, category,
    content='events', content_rowid='id'
);
-- Auto-sync triggers on INSERT and DELETE
```

### Indexes
- `idx_events_created` — created_at DESC
- `idx_events_priority` — priority
- `idx_events_region` — region
- `idx_events_flashpoint` — flashpoint
- `idx_events_source_type` — source_type
- `idx_events_dedup` — dedup_hash

### Features
- WAL mode for concurrent reads/writes
- 6-hour exact dedup window per hash
- Cross-source fuzzy dedup (Jaccard 0.55, 3-hour window, last 200 titles)
- 7-day default feed freshness (pinned events bypass)
- 90-day retention (configurable via RETENTION_DAYS)

---

## FTS5 Search

### Power Tracker Keywords

All keywords are double-quoted in FTS5 queries to prevent hyphen/number parsing issues (e.g., `s-400` would be parsed as `s NOT 400` without quoting).

| Power | Keywords (sample) |
|-------|-------------------|
| **US** (27) | united states, pentagon, biden, trump, centcom, indopacom, white house, us military, state department, us navy, us air force, us army, cia, nsa, f-35, b-21, carrier strike, tomahawk, ohio class, virginia class, arleigh burke, nimitz, gerald ford, secretary of defense, joint chiefs, africom, eucom, southcom |
| **China** (23) | china, beijing, xi jinping, south china sea, chinese military, ccp, taiwan strait, people's liberation army, pla navy, plaaf, type 003, type 055, df-41, df-26, j-20, j-35, liaoning, shandong, fujian, nine-dash line, wolf warrior, belt and road, central military commission, rocket force, eastern theater, southern theater |
| **Russia** (22) | russia, moscow, putin, wagner, black sea fleet, russian military, kremlin, donbas, ukraine, iskander, kalibr, sukhoi, kilo class, borei, tsirkon, zircon, shoigu, gerasimov, belousov, northern fleet, pacific fleet, s-300, s-400, su-57, tu-160, tu-95 |
| **EU/NATO** (23) | nato, european union, brussels, stoltenberg, bundeswehr, royal navy, royal air force, french military, macron defence, article 5, allied command, european defence, eu defence, eurocorps, rutte, european council, eunavfor, standing naval force, jef, efp, enhanced forward presence, saceur, shape, nato response force, leopard 2, eurofighter, fremm, type 26 |

### Query Construction
All keywords are double-quoted (`"keyword"`) for safe FTS5 parsing. Combined with OR operator. Results exclude map-only source types and India-region events. Filtered to 7-day freshness window. Sorted by priority then date.

---

## API Endpoints

### Dashboard Routes

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard page |

### HTMX Partial Routes

| Endpoint | Method | Params | Returns |
|----------|--------|--------|---------|
| `/partials/feed` | GET | `region`, `limit`, `min_priority` | Feed panel HTML |
| `/partials/india` | GET | `category` | India Command HTML |
| `/partials/powers` | GET | `country` (us/china/russia/eu_nato) | Powers panel HTML |
| `/partials/situation` | GET | — | Situation board HTML |
| `/partials/search` | GET | `q` (search query) | Search results HTML |
| `/events/{id}/read` | POST | — | Toggle read status |
| `/events/{id}/pin` | POST | — | Toggle pin status |

### JSON API Routes

| Endpoint | Method | Params | Returns |
|----------|--------|--------|---------|
| `/api/events/geojson` | GET | `hours`, `region`, `flashpoint`, `source_types`, `min_priority` | GeoJSON FeatureCollection |
| `/api/flashpoints` | GET | — | Flashpoint status array |
| `/api/search` | GET | `q`, `limit` | Event array |

### SSE Streams

| Endpoint | Event Types | Purpose |
|----------|------------|---------|
| `/sse/feed` | `new_event` | Real-time event cards |
| `/sse/alerts` | `alert` | Critical alert banners + sound |

---

## Dashboard UI (5 Panels)

```
┌─────────────────────────────────────────────────────────────┐
│  TOPBAR: Logo · Status Light · Search Bar · Refresh Timer   │
├──────────────────────┬──────────────────────────────────────┤
│                      │                                      │
│   CONFLICT MAP       │   BREAKING INTEL FEED               │
│   (Leaflet)          │   Tabs: All · High+ · India ·       │
│   5 map layers       │         MidEast · AsiaPac ·         │
│   Filter overlays    │         Europe · Africa              │
│   Flashpoint overlay │   SSE live updates with client-side  │
│   [Fullscreen]       │   filtering + "N new events" bar    │
│                      │                                      │
│  ← drag-resizable →  │                                      │
├──────────────────────┼──────────────────────────────────────┤
│                      │                                      │
│   INDIA COMMAND      │   GREAT POWER TRACKER               │
│   Tabs: All·Defence· │   Tabs: US · China · Russia · EU    │
│   LAC · Diplomacy ·  │   FTS5 keyword search per country   │
│   Space · Nuclear    │   Region exclusion (no India leak)  │
│                      │   7-day freshness window            │
│                      │                                      │
├──────────────────────┴──────────────────────────────────────┤
│                                                             │
│   SITUATION BOARD (full width)                              │
│   Flashpoint · Status · Score · Last Event · 24h · 7-Day   │
│   Sparkline trend charts per flashpoint                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Grid Layout
- Row 1: Map (2fr) | Feed (3fr) — drag-resizable vertical divider
- Row 2: India (2fr) | Powers (3fr)
- Row 3: Situation Board (full width)
- Horizontal drag handles between Row 1 and Row 2

### Map Layers (5)
- **Conflict** (orange): ACLED/UCDP geocoded conflict events
- **Thermal** (red): NASA FIRMS fire hotspots
- **Aviation** (blue): ADS-B military aircraft tracks
- **Seismic** (yellow): USGS earthquake markers
- **News** (red-orange): GDELT Geo geocoded news clusters

### Map Features
- Flashpoint overlay with zone boundaries
- Layer toggles with event counts
- Auto-zoom to region bounds on tab switch
- Tiered time windows: real-time (48h) for live sources, 90 days for UCDP/ACLED
- Fullscreen toggle

---

## Alert System

### Alert Routing

```
Event inserted
    │
    ├─ Map-only source (FIRMS/USGS/ADS-B/GDELT_GEO)?
    │   └─ Skip SSE & Telegram. DB only.
    │
    ├─ Historical source (UCDP)?
    │   └─ SSE + Dashboard only. No Telegram.
    │
    ├─ Boot suppression (first 3 min)?
    │   └─ SSE only. No Telegram.
    │
    ├─ CRITICAL + fresh (<60 min)?
    │   └─ Instant Telegram: text + photo + location + SSE alert banner
    │
    ├─ HIGH + fresh (<6 hours)?
    │   └─ Queue → 1-min batch Telegram (max 10 per batch)
    │
    └─ MEDIUM / LOW
        └─ Dashboard + SSE only
```

### Telegram Alert Format
```
🔴 CRITICAL PRIORITY

<b>Headline text</b>

Summary text (only if different from headline)

Source: Aurora Intel
Region: middle_east
Flashpoint: Iran-Israel-US
Goldstein: -7.0

Source Link
```

Duplicate headline suppression: if `summary` is identical to or starts with `title`, summary is omitted to prevent showing the same text twice.

---

## SSE System

### Server Side (sse.py + engine.py)
- Global subscriber list (asyncio.Queue per client)
- `broadcast_event(html)` → push to all /sse/feed subscribers
- `broadcast_alert(html)` → push to all /sse/alerts subscribers
- 30s keepalive heartbeat

### Client Side (dashboard.js)
- Tracks active filter: `{ region, minPriority }`
- SSE events carry `data-region` and `data-priority` attributes
- Events matching active filter → prepend to feed with fadeIn
- Non-matching events → increment hidden counter
- "N new events — Show All" notification bar
- Alert events → play sound + show banner for 30s

---

## Scheduler

| Job | Interval | Description |
|-----|----------|-------------|
| RSS Hot | 2 min | Wire services (Al Jazeera, BBC, Times of Israel) |
| RSS Warm | 10 min | Analysis/regional feeds |
| GDELT | 15 min | 8 conflict keyword queries |
| GDELT Geo | 30 min | 6 geocoded conflict queries (map-only) |
| Telegram | 2 min | 15 OSINT channels (relevance gated) |
| ADS-B | 5 min | Military aircraft (3 fallback APIs) |
| USGS | 30 min | Earthquakes M4.5+ |
| ACLED | 60 min | Conflict events (OAuth2) |
| FIRMS | 60 min | Thermal anomalies (5 zones) |
| UCDP | 6 hours | Uppsala conflict CSV |
| Flush HIGH batch | 1 min | Send queued HIGH alerts to Telegram |
| Flush MEDIUM batch | 15 min | No-op (medium stays on dashboard) |
| Prune old events | 24 hours | Delete unpinned >90 days |

---

## Security

### HTTP Headers (middleware)
- **CSP**: self + inline scripts/styles + Leaflet tiles (basemaps.cartocdn.com) + Telegram images (t.me) + NASA FIRMS images (eosdis.nasa.gov)
- **X-Frame-Options**: DENY
- **X-Content-Type-Options**: nosniff
- **Referrer-Policy**: no-referrer

### Anti-Fingerprinting
- User-Agent rotation (10 agent pool)
- ±30s jitter between collection cycles
- Staggered requests (1-3s between feeds)

### Data Integrity
- Two-phase deduplication (exact MD5 + fuzzy Jaccard)
- WAL mode for safe concurrent access
- Configurable retention cleanup
- All keyword matching uses word boundaries (no substring false positives)
- FTS5 keywords double-quoted to prevent parser issues with hyphens/numbers

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search bar |
| `Escape` | Close search / exit fullscreen |
| `1-5` | Jump to panel |
| `R` | Reload page |
| `F` | Toggle map fullscreen |

---

## Environment Variables (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Chat ID from @userinfobot |
| `ACLED_EMAIL` | No | ACLED account email |
| `ACLED_PASSWORD` | No | ACLED account password |
| `FIRMS_MAP_KEY` | No | NASA FIRMS API key |
| `GOLDSTEIN_CRITICAL` | No | Threshold (default: -8) |
| `GOLDSTEIN_HIGH` | No | Threshold (default: -5) |
| `GOLDSTEIN_MEDIUM` | No | Threshold (default: -3) |
| `RETENTION_DAYS` | No | Event retention (default: 90) |
| `HTTP_PROXY` / `HTTPS_PROXY` | No | Proxy configuration |

---

## Running

### Windows
```
start.bat          # double-click → builds, starts, opens browser
stop.bat           # double-click → stops container
share.bat          # double-click → shows local + network URL
```

### Mac
```
setup_mac.command   # one-time: open Terminal, type: bash setup_mac.command
start_mac.command   # double-click → builds, starts, opens browser
stop_mac.command    # double-click → stops container
share_mac.command   # double-click → starts Cloudflare tunnel, shows public URL
```
First time only: open Terminal, type `bash `, then drag `setup_mac.command` into the Terminal window (this pastes the path), then press Enter. This makes all scripts double-clickable. Then right-click → Open on first use (macOS blocks unsigned scripts the very first time).

### Manual (any platform)
```bash
docker compose up -d --build     # start
docker compose down              # stop
docker logs -f osint-warroom     # view logs
# Access: http://localhost:8000
```

### Remote Access (Share from Anywhere)
The share scripts use **Cloudflare Tunnel** (`cloudflared`) to create a public HTTPS URL for the dashboard — accessible from anywhere in the world, while still hosted on your machine. No port forwarding, no static IP, no account needed.

Double-click `share.bat` (Windows) or `share_mac.command` (Mac):
1. Installs `cloudflared` automatically if missing (via `winget` / `brew`)
2. Starts a tunnel to `localhost:8000`
3. Prints a public URL like `https://random-words.trycloudflare.com`
4. Share that URL with anyone — works on phone, tablet, another computer
5. Tunnel stays open until you close the window

Also shows the LAN URL (`http://<your-ip>:8000`) for devices on the same Wi-Fi.

### Platform Notes
- **Windows**: Requires Docker Desktop. Double-click the `.bat` files.
- **Mac**: Requires Docker Desktop for Mac. Double-click the `.command` files.
- All application code, Docker config, and data are fully cross-platform. The scripts are just convenience wrappers around `docker compose`.
