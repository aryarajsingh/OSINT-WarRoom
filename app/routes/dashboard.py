import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.config import TEMPLATES_DIR, FLASHPOINTS, MAP_ONLY_SOURCE_TYPES
from app.database import get_events, get_events_for_india, get_events_for_power
from app.processing.situation import compute_all_flashpoints

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    feed_events = await get_events(limit=30, exclude_source_types=MAP_ONLY_SOURCE_TYPES)
    india_events = await get_events_for_india(limit=20)
    powers_events = await get_events_for_power("us", limit=20)
    flashpoints = await compute_all_flashpoints()

    # Build flashpoint geo data for JS map focus system
    flashpoint_geo = []
    for fp in flashpoints:
        config = FLASHPOINTS.get(fp["name"], {})
        flashpoint_geo.append({
            "name": fp["name"],
            "lat": config.get("lat", 0),
            "lon": config.get("lon", 0),
            "radius_km": config.get("radius_km", 500),
            "status": fp["status"],
            "score": fp["score"],
            "event_count_24h": fp["event_count_24h"],
        })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "feed_events": feed_events,
        "india_events": india_events,
        "powers_events": powers_events,
        "flashpoints": flashpoints,
        "flashpoint_geo_json": json.dumps(flashpoint_geo),
    })
