"""GDELT geographic data collector — fetches geocoded news events for the map.

Uses GDELT DOC 2.0 API in PointData mode to get lat/lon clusters of conflict articles.
These are map-only events (no feed card) that show WHERE news is being reported from.
"""
import logging
import asyncio
import httpx
from app.config import get_httpx_kwargs
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.gdelt_geo")

GDELT_DOC_API = "http://api.gdeltproject.org/api/v2/doc/doc"

# Focused conflict queries for geographic mapping
GEO_QUERIES = [
    '(airstrike OR "missile strike" OR bombing OR shelling)',
    '("border clash" OR "military buildup" OR "troop deployment")',
    '("Iran Israel" OR Hezbollah OR Houthi)',
    '("South China Sea" OR "Taiwan strait" OR "PLA navy")',
    '(Ukraine OR Russia OR "black sea")',
    '("India China" OR LAC OR Ladakh)',
]


async def collect_gdelt_geo():
    """Fetch geocoded conflict events from GDELT for the map layer."""
    logger.info("Collecting GDELT geo data for map")
    total_inserted = 0

    for query in GEO_QUERIES:
        try:
            params = {
                "query": query,
                "mode": "PointData",
                "maxpoints": "50",
                "format": "json",
                "timespan": "24h",
            }

            kwargs = get_httpx_kwargs()
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(GDELT_DOC_API, params=params, timeout=30.0)
                resp.raise_for_status()

            body = resp.text.strip()
            if not body or not body.startswith(("{", "[")):
                continue

            try:
                data = resp.json()
            except Exception:
                continue

            # PointData returns array of geographic points
            # Each point: {lat, lon, name, html, ...}
            points = []
            if isinstance(data, list):
                points = data
            elif isinstance(data, dict):
                # Sometimes wrapped in an object
                points = data.get("features", data.get("points", []))
                if not points and "lat" in data:
                    points = [data]

            for point in points:
                lat = point.get("lat") or point.get("latitude")
                lon = point.get("lon") or point.get("lng") or point.get("longitude")

                if not lat or not lon:
                    continue

                try:
                    lat = float(lat)
                    lon = float(lon)
                except (ValueError, TypeError):
                    continue

                # Skip obviously bad coordinates
                if abs(lat) < 0.1 and abs(lon) < 0.1:
                    continue

                name = point.get("name", "") or point.get("locationname", "")
                count = point.get("count", 1) or point.get("numentions", 1)
                html = point.get("html", "") or point.get("context", "")

                title = name if name else f"GDELT activity at {lat:.2f}, {lon:.2f}"
                if count and int(count) > 1:
                    title = f"{title} ({count} reports)"

                event = {
                    "title": title[:500],
                    "summary": html[:2000] if html else f"Geographic cluster of {count} conflict-related articles",
                    "url": "",
                    "source": "GDELT Geo",
                    "source_type": "gdelt_geo",
                    "lat": lat,
                    "lon": lon,
                }

                event = classify_event(event)
                result = await insert_event(event)
                if result:
                    total_inserted += 1

            await asyncio.sleep(1)

        except httpx.ConnectTimeout:
            logger.warning("GDELT GEO API unreachable (timeout)")
            break
        except httpx.ConnectError:
            logger.warning("GDELT GEO API connection refused")
            break
        except Exception as e:
            logger.warning(f"GDELT GEO query failed: {type(e).__name__}: {e}")
            continue

    logger.info(f"GDELT GEO: inserted {total_inserted} new map events")
    return total_inserted
