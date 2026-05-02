import csv
import io
import logging
import hashlib
from datetime import datetime, timezone, timedelta
import httpx
from app.config import get_httpx_kwargs, COUNTRY_REGION_MAP
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.ucdp")

# UCDP GED Candidate dataset — free CSV download, no auth needed
# Updated monthly with ~1 month lag, covers global conflict events
UCDP_CANDIDATE_URL = "https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_0_1.csv"

# Violence type mapping
VIOLENCE_TYPES = {
    1: "State-based conflict",
    2: "Non-state conflict",
    3: "One-sided violence",
}


async def collect_ucdp():
    """Fetch conflict events from UCDP GED Candidate dataset (CSV download)."""
    logger.info("Collecting UCDP conflict events")

    try:
        kwargs = get_httpx_kwargs()
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(UCDP_CANDIDATE_URL, timeout=30.0)
            resp.raise_for_status()

        body = resp.text.strip()
        if not body:
            logger.warning("UCDP returned empty response")
            return 0

        reader = csv.DictReader(io.StringIO(body))

        # Only insert events from the last 90 days to avoid flooding the DB
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
        inserted = 0

        for row in reader:
            try:
                date_start = row.get("date_start", "")
                if not date_start or date_start < cutoff:
                    continue

                country = row.get("country", "Unknown")
                side_a = row.get("side_a", "")
                side_b = row.get("side_b", "")
                conflict_name = row.get("conflict_name", "")
                violence_type = int(row.get("type_of_violence", 0))
                violence_label = VIOLENCE_TYPES.get(violence_type, "Conflict")

                best_deaths = int(row.get("best", 0) or 0)
                deaths_civilians = int(row.get("deaths_civilians", 0) or 0)
                high_deaths = int(row.get("high", 0) or 0)

                lat = row.get("latitude")
                lon = row.get("longitude")
                where_desc = row.get("where_description", "")
                adm1 = row.get("adm_1", "")

                # Build title
                location = where_desc or adm1 or country
                if side_a and side_b:
                    title = f"{side_a} vs {side_b} — {violence_label} in {location}"
                else:
                    title = f"{violence_label} in {location}, {country}"

                # Build summary
                parts = []
                if conflict_name:
                    parts.append(f"Conflict: {conflict_name}")
                if best_deaths > 0:
                    parts.append(f"Deaths: {best_deaths} (range {row.get('low', '?')}-{high_deaths})")
                if deaths_civilians > 0:
                    parts.append(f"Civilian deaths: {deaths_civilians}")
                source_article = row.get("source_article", "")
                if source_article:
                    parts.append(f"Source: {source_article[:150]}")
                summary = ". ".join(parts)

                # Goldstein score based on violence type and fatalities
                if best_deaths >= 50:
                    goldstein = -10
                elif best_deaths >= 10:
                    goldstein = -9
                elif violence_type == 3:  # One-sided violence
                    goldstein = -9
                elif violence_type == 1:  # State-based
                    goldstein = -8
                else:
                    goldstein = -6

                # Dedup hash
                dedup = hashlib.md5(
                    f"ucdp-{row.get('id', '')}-{date_start}".encode()
                ).hexdigest()

                event = {
                    "title": title[:500],
                    "summary": summary[:2000],
                    "url": f"https://ucdp.uu.se/event/{row.get('id', '')}",
                    "source": "UCDP",
                    "source_type": "ucdp",
                    "region": COUNTRY_REGION_MAP.get(country, ""),
                    "goldstein": goldstein,
                    "lat": float(lat) if lat else None,
                    "lon": float(lon) if lon else None,
                    "fatalities": best_deaths,
                    "dedup_hash": dedup,
                    "created_at": date_start,
                }

                event = classify_event(event)
                result = await insert_event(event)
                if result:
                    inserted += 1

            except (ValueError, KeyError) as e:
                continue

        logger.info(f"UCDP: inserted {inserted} new conflict events")
        return inserted

    except Exception as e:
        logger.error(f"UCDP collection failed: {type(e).__name__}: {e}")
        return 0
