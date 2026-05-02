import logging
import httpx
import asyncio
from app.config import get_httpx_kwargs
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.gdelt")

# IMPORTANT: GDELT's HTTPS (port 443) is broken — HTTP works fine
GDELT_DOC_API = "http://api.gdeltproject.org/api/v2/doc/doc"
GDELT_CONTEXT_API = "http://api.gdeltproject.org/api/v2/context/context"

# Conflict-focused queries — GDELT requires () around OR-ed terms
QUERIES = [
    '(airstrike OR "missile strike" OR bombing OR "military attack")',
    '("border clash" OR "border incursion" OR "military buildup")',
    '(nuclear OR ICBM OR "ballistic missile")',
    '("India China border" OR "LAC standoff" OR Pangong OR Galwan)',
    '("Iran Israel" OR Hezbollah OR Houthi OR IRGC)',
    '("South China Sea" OR "Taiwan strait" OR "PLA navy")',
    '(sanctions OR "trade war" OR blockade)',
    '("military exercise" OR "naval deployment" OR "carrier strike group")',
]


async def collect_gdelt():
    """Fetch conflict-related events from GDELT DOC 2.0 API (HTTP only)."""
    logger.info("Collecting GDELT events")
    total_inserted = 0

    for query in QUERIES:
        try:
            params = {
                "query": query,
                "mode": "ArtList",
                "maxrecords": "25",
                "format": "json",
                "timespan": "1h",  # Minimum reliable window
                "sort": "datedesc",
            }

            kwargs = get_httpx_kwargs()
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(
                    GDELT_DOC_API, params=params, timeout=30.0
                )
                resp.raise_for_status()

            # GDELT returns empty body or error text when no results
            body = resp.text.strip()
            if not body or not body.startswith("{"):
                if body:
                    logger.debug(f"GDELT non-JSON response: {body[:100]}")
                continue

            try:
                data = resp.json()
            except Exception:
                continue

            articles = data.get("articles", [])
            for article in articles:
                title = article.get("title", "").strip()
                if not title:
                    continue

                # Extract tone/Goldstein from GDELT (tone field is composite)
                tone = article.get("tone", 0)
                goldstein = None
                if isinstance(tone, (int, float)):
                    # GDELT tone: negative = conflict, scale roughly -10 to +10
                    goldstein = tone

                lat = article.get("sourcecountylat")
                lon = article.get("sourcecountylon")

                # Try geo from article
                if not lat and "seendate" in article:
                    lat = article.get("latitude")
                    lon = article.get("longitude")

                event = {
                    "title": title,
                    "summary": article.get("excerpt", "")[:2000],
                    "url": article.get("url", ""),
                    "source": article.get("domain", "GDELT"),
                    "source_type": "gdelt",
                    "goldstein": goldstein,
                    "lat": float(lat) if lat else None,
                    "lon": float(lon) if lon else None,
                    "image_url": article.get("socialimage", ""),
                }

                event = classify_event(event)
                result = await insert_event(event)
                if result:
                    total_inserted += 1

            # Small delay between queries to be polite to GDELT
            await asyncio.sleep(1)

        except httpx.ConnectTimeout:
            logger.warning("GDELT API unreachable (connect timeout) — may be down")
            break  # Don't retry other queries if API is unreachable
        except httpx.ConnectError:
            logger.warning("GDELT API connection refused — service may be down")
            break
        except Exception as e:
            logger.warning(f"GDELT query failed: {type(e).__name__}: {e}")
            continue

    logger.info(f"GDELT: inserted {total_inserted} new events")
    return total_inserted
