import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.database import get_map_events, search_events, toggle_read, toggle_pin
from app.processing.situation import compute_all_flashpoints

router = APIRouter(prefix="/api")


@router.get("/events/geojson")
async def events_geojson(
    hours: int = 48,
    region: str = "",
    flashpoint: str = "",
    source_types: str = "",
    min_priority: str = "",
):
    """GeoJSON FeatureCollection for the conflict map."""
    st_list = [s.strip() for s in source_types.split(",") if s.strip()] or None
    events = await get_map_events(
        hours=hours,
        region=region,
        flashpoint=flashpoint,
        source_types=st_list,
        min_priority=min_priority,
    )

    features = []
    for e in events:
        if e["lat"] is None or e["lon"] is None:
            continue

        # Color by event type
        color_map = {
            "firms": "#ff4444",      # red - thermal/strikes
            "acled": "#ff8800",      # orange - conflict events
            "ucdp": "#ff8800",       # orange - conflict events (same as ACLED)
            "usgs": "#ffcc00",       # yellow - seismic
            "adsb": "#4488ff",       # blue - military aviation
            "gdelt": "#ff6644",      # red-orange - news events
            "gdelt_geo": "#ff6644",  # red-orange - geocoded news
            "telegram": "#aa44ff",   # purple - OSINT channels
        }
        color = color_map.get(e["source_type"], "#888888")

        priority_size = {
            "critical": 12,
            "high": 9,
            "medium": 6,
            "low": 4,
        }
        size = priority_size.get(e["priority"], 4)

        # Determine layer group (collapse related source_types)
        layer_map = {
            "acled": "conflict", "ucdp": "conflict",
            "adsb": "aviation",
            "firms": "thermal",
            "usgs": "seismic",
            "gdelt": "news", "gdelt_geo": "news",
            "telegram": "news", "rss": "news",
        }
        layer = layer_map.get(e["source_type"], "other")

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [e["lon"], e["lat"]],
            },
            "properties": {
                "id": e["id"],
                "title": e["title"],
                "summary": (e.get("summary") or "")[:200],
                "url": e.get("url", ""),
                "source": e["source"],
                "source_type": e["source_type"],
                "source_tier": e.get("source_tier", ""),
                "priority": e["priority"],
                "flashpoint": e["flashpoint"],
                "region": e.get("region", ""),
                "created_at": e["created_at"],
                "color": color,
                "size": size,
                "layer": layer,
            },
        })

    return JSONResponse({
        "type": "FeatureCollection",
        "features": features,
    })


@router.get("/flashpoints")
async def flashpoints():
    """Current flashpoint statuses for the situation board."""
    data = await compute_all_flashpoints()
    return JSONResponse(data)


@router.get("/search")
async def api_search(q: str = "", limit: int = 50):
    if not q or len(q) < 2:
        return JSONResponse([])
    events = await search_events(q, limit=limit)
    return JSONResponse(events)


@router.post("/events/{event_id}/read")
async def mark_read(event_id: int):
    await toggle_read(event_id)
    return JSONResponse({"ok": True})


@router.post("/events/{event_id}/pin")
async def pin_event(event_id: int):
    await toggle_pin(event_id)
    return JSONResponse({"ok": True})
