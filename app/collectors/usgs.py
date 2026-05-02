import logging
import httpx
from app.config import get_httpx_kwargs
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.usgs")

USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"


async def collect_usgs():
    """Fetch M4.5+ earthquakes from USGS (also detects large explosions)."""
    logger.info("Collecting USGS seismic events")

    try:
        params = {
            "format": "geojson",
            "minmagnitude": "4.5",
            "orderby": "time",
            "limit": "50",
        }

        kwargs = get_httpx_kwargs()
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(USGS_API, params=params)
            resp.raise_for_status()
            data = resp.json()

        features = data.get("features", [])
        inserted = 0

        for f in features:
            props = f.get("properties", {})
            geom = f.get("geometry", {})
            coords = geom.get("coordinates", [])

            if len(coords) < 2:
                continue

            mag = props.get("mag", 0)
            place = props.get("place", "Unknown location")
            url = props.get("url", "")
            event_type = props.get("type", "earthquake")

            title = f"M{mag:.1f} {event_type} — {place}"

            event = {
                "title": title,
                "summary": f"Magnitude {mag:.1f} {event_type} at depth {coords[2]:.0f}km. {place}.",
                "url": url,
                "source": "USGS",
                "source_type": "usgs",
                "lat": coords[1],
                "lon": coords[0],
                "goldstein": -2 if mag < 6 else -5,
            }

            event = classify_event(event)
            result = await insert_event(event)
            if result:
                inserted += 1

        logger.info(f"USGS: inserted {inserted} new seismic events")
        return inserted

    except Exception as e:
        logger.error(f"USGS collection failed: {e}")
        return 0
