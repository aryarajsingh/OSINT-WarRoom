import aiosqlite
import asyncio
from app.config import DB_PATH, DATA_DIR

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    url TEXT DEFAULT '',
    source TEXT DEFAULT '',
    source_type TEXT DEFAULT 'rss',
    source_tier TEXT DEFAULT 'UNKNOWN',
    region TEXT DEFAULT '',
    category TEXT DEFAULT '',
    priority TEXT DEFAULT 'low',
    goldstein REAL,
    lat REAL,
    lon REAL,
    image_url TEXT DEFAULT '',
    fatalities INTEGER DEFAULT 0,
    flashpoint TEXT DEFAULT '',
    is_read INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    dedup_hash TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority);
CREATE INDEX IF NOT EXISTS idx_events_region ON events(region);
CREATE INDEX IF NOT EXISTS idx_events_flashpoint ON events(flashpoint);
CREATE INDEX IF NOT EXISTS idx_events_source_type ON events(source_type);
CREATE INDEX IF NOT EXISTS idx_events_dedup ON events(dedup_hash);

-- Full-text search index
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    title, summary, source, region, category,
    content='events',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, title, summary, source, region, category)
    VALUES (new.id, new.title, new.summary, new.source, new.region, new.category);
END;

CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, summary, source, region, category)
    VALUES ('delete', old.id, old.title, old.summary, old.source, old.region, old.category);
END;
"""


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(DB_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL;")
        await _db.execute("PRAGMA foreign_keys=ON;")
        await _db.executescript(SCHEMA)
        await _db.commit()
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def insert_event(event: dict) -> int | None:
    """Insert event if not duplicate. Returns row id or None if duplicate.
    Also triggers alert processing for new events."""
    db = await get_db()

    # Phase 1: Exact dedup (same source, same title hash within 6 hours)
    if event.get("dedup_hash"):
        cursor = await db.execute(
            "SELECT id FROM events WHERE dedup_hash = ? AND created_at > datetime('now', '-6 hours')",
            (event["dedup_hash"],)
        )
        if await cursor.fetchone():
            return None

    # Phase 2: Cross-source fuzzy dedup (different sources, similar titles within 3 hours)
    title = event.get("title", "")
    if title and len(title) > 20:
        cursor = await db.execute(
            "SELECT title FROM events WHERE created_at > datetime('now', '-3 hours') ORDER BY created_at DESC LIMIT 200",
        )
        rows = await cursor.fetchall()
        if rows:
            from app.processing.dedup import is_duplicate
            recent_titles = [row["title"] for row in rows]
            if is_duplicate(title, recent_titles, threshold=0.55):
                return None

    cols = [k for k in event.keys() if k != "id"]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    values = [event[k] for k in cols]

    cursor = await db.execute(
        f"INSERT INTO events ({col_names}) VALUES ({placeholders})",
        values
    )
    await db.commit()

    event_id = cursor.lastrowid
    event["id"] = event_id

    # Trigger alert processing (non-blocking)
    try:
        from app.alerts.engine import process_event_alert
        import asyncio
        asyncio.create_task(process_event_alert(event))
    except Exception:
        pass  # Don't let alert failures break data collection

    return event_id


async def get_events(
    limit: int = 50,
    offset: int = 0,
    region: str = "",
    source_type: str = "",
    priority: str = "",
    flashpoint: str = "",
    category: str = "",
    pinned_first: bool = True,
    exclude_source_types: tuple = (),
    min_priority: str = "",
    max_age_days: int = 7,
) -> list[dict]:
    db = await get_db()

    conditions = []
    params = []

    # Time window: only return events from last N days (pinned events always shown)
    if max_age_days > 0:
        conditions.append("(created_at > datetime('now', ?) OR is_pinned = 1)")
        params.append(f"-{max_age_days} days")

    if region:
        conditions.append("region = ?")
        params.append(region)
    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    if min_priority:
        # Filter to events at or above a priority threshold
        allowed = _priority_at_or_above(min_priority)
        if allowed:
            placeholders = ", ".join(["?"] * len(allowed))
            conditions.append(f"priority IN ({placeholders})")
            params.extend(allowed)
    if flashpoint:
        conditions.append("flashpoint = ?")
        params.append(flashpoint)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if exclude_source_types:
        placeholders = ", ".join(["?"] * len(exclude_source_types))
        conditions.append(f"source_type NOT IN ({placeholders})")
        params.extend(exclude_source_types)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    # Sort: pinned first, then priority (critical > high > medium > low), then newest
    priority_order = """CASE priority
        WHEN 'critical' THEN 0 WHEN 'high' THEN 1
        WHEN 'medium' THEN 2 ELSE 3 END"""
    if pinned_first:
        order = f"ORDER BY is_pinned DESC, {priority_order}, created_at DESC"
    else:
        order = f"ORDER BY {priority_order}, created_at DESC"

    cursor = await db.execute(
        f"SELECT * FROM events {where} {order} LIMIT ? OFFSET ?",
        params + [limit, offset]
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def _priority_at_or_above(level: str) -> list[str]:
    """Return list of priority values at or above the given level."""
    hierarchy = ["critical", "high", "medium", "low"]
    try:
        idx = hierarchy.index(level.lower())
        return hierarchy[:idx + 1]
    except ValueError:
        return []


async def get_events_for_region(region: str, limit: int = 30) -> list[dict]:
    """Get events filtered by region keyword matching."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM events WHERE region = ? ORDER BY is_pinned DESC, created_at DESC LIMIT ?",
        (region, limit)
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_events_for_india(category: str = "", limit: int = 30, max_age_days: int = 7) -> list[dict]:
    db = await get_db()
    priority_order = """CASE priority
        WHEN 'critical' THEN 0 WHEN 'high' THEN 1
        WHEN 'medium' THEN 2 ELSE 3 END"""

    conditions = ["region = 'india'", "(created_at > datetime('now', ?) OR is_pinned = 1)"]
    params: list = [f"-{max_age_days} days"]

    if category:
        conditions.append("category = ?")
        params.append(category)

    where = "WHERE " + " AND ".join(conditions)
    cursor = await db.execute(
        f"SELECT * FROM events {where} ORDER BY is_pinned DESC, {priority_order}, created_at DESC LIMIT ?",
        params + [limit]
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_events_for_power(country: str, limit: int = 30) -> list[dict]:
    """Get events about a specific great power using FTS5 full-text search."""
    db = await get_db()

    # Map country codes to search keywords (cleaned to avoid false positives)
    power_keywords = {
        "us": [
            "united states", "pentagon", "biden", "trump", "centcom", "indopacom",
            "white house", "us military", "state department", "us navy",
            "us air force", "us army",
            "cia", "nsa", "f-35", "b-21",
            "carrier strike", "tomahawk", "ohio class",
            "virginia class", "arleigh burke", "nimitz",
            "gerald ford", "secretary of defense",
            "joint chiefs", "africom", "eucom", "southcom",
        ],
        "china": [
            "china", "beijing", "xi jinping", "south china sea",
            "chinese military", "ccp", "taiwan strait",
            "people's liberation army", "pla navy", "plaaf",
            "type 003", "type 055", "df-41", "df-26", "j-20", "j-35",
            "liaoning", "shandong", "fujian",
            "nine-dash line", "wolf warrior", "belt and road",
            "central military commission", "rocket force",
            "eastern theater", "southern theater",
        ],
        "russia": [
            "russia", "moscow", "putin", "wagner", "black sea fleet",
            "russian military", "kremlin", "donbas", "ukraine",
            "iskander", "kalibr", "sukhoi", "kilo class",
            "borei", "tsirkon", "zircon",
            "shoigu", "gerasimov", "belousov",
            "northern fleet", "pacific fleet",
            "s-300", "s-400", "su-57", "tu-160", "tu-95",
        ],
        "eu_nato": [
            "nato", "european union", "brussels", "stoltenberg",
            "bundeswehr", "royal navy", "royal air force",
            "french military", "macron defence", "article 5",
            "allied command", "european defence", "eu defence",
            "eurocorps", "raf lakenheath", "raf coningsby",
            "rutte", "european council", "eunavfor",
            "standing naval force", "jef", "efp",
            "enhanced forward presence", "saceur", "shape",
            "nato response force",
            "leopard 2", "eurofighter", "fremm", "type 26",
        ],
    }

    keywords = power_keywords.get(country, [country])

    # Build FTS5 query: quote ALL keywords to handle hyphens, numbers, etc.
    # FTS5 interprets unquoted hyphens as NOT operators (e.g., s-400 = s NOT 400)
    fts_terms = []
    for kw in keywords:
        kw = kw.strip()
        fts_terms.append(f'"{kw}"')
    fts_query = " OR ".join(fts_terms)

    cursor = await db.execute(
        """SELECT e.* FROM events e
           JOIN events_fts f ON e.id = f.rowid
           WHERE events_fts MATCH ?
             AND e.source_type NOT IN ('firms', 'usgs', 'adsb')
             AND e.region != 'india'
             AND (e.created_at > datetime('now', '-7 days') OR e.is_pinned = 1)
           ORDER BY e.is_pinned DESC,
                  CASE e.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                  WHEN 'medium' THEN 2 ELSE 3 END,
                  e.created_at DESC
           LIMIT ?""",
        (fts_query, limit)
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def search_events(query: str, limit: int = 50) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT e.*, highlight(events_fts, 0, '<mark>', '</mark>') as highlighted_title
           FROM events e
           JOIN events_fts f ON e.id = f.rowid
           WHERE events_fts MATCH ?
           ORDER BY rank LIMIT ?""",
        (query, limit)
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_map_events(
    hours: int = 48,
    region: str = "",
    flashpoint: str = "",
    source_types: list[str] | None = None,
    min_priority: str = "",
) -> list[dict]:
    """Get geocoded events for the map.
    Uses tiered time windows: real-time sources (48h), conflict databases (90 days)."""
    db = await get_db()

    conditions = [
        "lat IS NOT NULL",
        "lon IS NOT NULL",
    ]
    params: list = []

    # Tiered time window: conflict databases use longer window (90 days),
    # real-time sources use the specified hours (default 48h)
    # This ensures UCDP/ACLED events (with historical event dates) appear on the map
    conditions.append("""(
        (source_type IN ('ucdp', 'acled') AND created_at > datetime('now', '-90 days'))
        OR (source_type NOT IN ('ucdp', 'acled') AND created_at > datetime('now', ?))
    )""")
    params.append(f"-{hours} hours")

    if region:
        conditions.append("region = ?")
        params.append(region)
    if flashpoint:
        conditions.append("flashpoint = ?")
        params.append(flashpoint)
    if source_types:
        placeholders = ", ".join(["?"] * len(source_types))
        conditions.append(f"source_type IN ({placeholders})")
        params.extend(source_types)
    if min_priority:
        allowed = _priority_at_or_above(min_priority)
        if allowed:
            placeholders = ", ".join(["?"] * len(allowed))
            conditions.append(f"priority IN ({placeholders})")
            params.extend(allowed)

    where = "WHERE " + " AND ".join(conditions)

    cursor = await db.execute(
        f"""SELECT id, title, summary, url, source, source_type, source_tier,
                  priority, lat, lon, goldstein, flashpoint, created_at,
                  category, region
           FROM events
           {where}
           ORDER BY created_at DESC
           LIMIT 2000""",
        params
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_flashpoint_stats(flashpoint: str, days: int = 7) -> dict:
    db = await get_db()

    # Event count last 24h
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM events WHERE flashpoint = ? AND created_at > datetime('now', '-1 day')",
        (flashpoint,)
    )
    row = await cursor.fetchone()
    count_24h = row["cnt"]

    # Average Goldstein last 24h
    cursor = await db.execute(
        "SELECT AVG(goldstein) as avg_g FROM events WHERE flashpoint = ? AND goldstein IS NOT NULL AND created_at > datetime('now', '-1 day')",
        (flashpoint,)
    )
    row = await cursor.fetchone()
    avg_goldstein = row["avg_g"] or 0

    # FIRMS thermal count in flashpoint zone last 24h
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM events WHERE flashpoint = ? AND source_type = 'firms' AND created_at > datetime('now', '-1 day')",
        (flashpoint,)
    )
    row = await cursor.fetchone()
    firms_count = row["cnt"]

    # Source diversity last 24h
    cursor = await db.execute(
        "SELECT COUNT(DISTINCT source) as cnt FROM events WHERE flashpoint = ? AND created_at > datetime('now', '-1 day')",
        (flashpoint,)
    )
    row = await cursor.fetchone()
    source_diversity = row["cnt"]

    # Total fatalities last 24h
    cursor = await db.execute(
        "SELECT COALESCE(SUM(fatalities), 0) as total FROM events WHERE flashpoint = ? AND created_at > datetime('now', '-1 day')",
        (flashpoint,)
    )
    row = await cursor.fetchone()
    fatalities = row["total"]

    # 7-day daily counts for sparkline
    daily_counts = []
    for i in range(7, 0, -1):
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE flashpoint = ? AND created_at BETWEEN datetime('now', ?) AND datetime('now', ?)",
            (flashpoint, f"-{i} days", f"-{i-1} days")
        )
        row = await cursor.fetchone()
        daily_counts.append(row["cnt"])

    # Last event time
    cursor = await db.execute(
        "SELECT created_at FROM events WHERE flashpoint = ? ORDER BY created_at DESC LIMIT 1",
        (flashpoint,)
    )
    row = await cursor.fetchone()
    last_event = row["created_at"] if row else None

    return {
        "count_24h": count_24h,
        "avg_goldstein": avg_goldstein,
        "firms_count": firms_count,
        "source_diversity": source_diversity,
        "fatalities": fatalities,
        "daily_counts": daily_counts,
        "last_event": last_event,
    }


async def toggle_read(event_id: int):
    db = await get_db()
    await db.execute("UPDATE events SET is_read = NOT is_read WHERE id = ?", (event_id,))
    await db.commit()


async def toggle_pin(event_id: int):
    db = await get_db()
    await db.execute("UPDATE events SET is_pinned = NOT is_pinned WHERE id = ?", (event_id,))
    await db.commit()


async def prune_old_events(days: int):
    db = await get_db()
    await db.execute(
        "DELETE FROM events WHERE created_at < datetime('now', ?) AND is_pinned = 0",
        (f"-{days} days",)
    )
    await db.commit()
