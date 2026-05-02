from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.config import TEMPLATES_DIR, MAP_ONLY_SOURCE_TYPES
from app.database import (
    get_events, get_events_for_india, get_events_for_power,
    search_events, toggle_read, toggle_pin,
)
from app.processing.situation import compute_all_flashpoints

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/partials/feed", response_class=HTMLResponse)
async def feed_partial(request: Request, region: str = "", limit: int = 30, min_priority: str = ""):
    events = await get_events(
        limit=limit,
        region=region if region != "all" else "",
        exclude_source_types=MAP_ONLY_SOURCE_TYPES,
        min_priority=min_priority,
    )
    return templates.TemplateResponse("partials/feed_panel.html", {
        "request": request,
        "events": events,
        "active_region": region or "all",
    })


@router.get("/partials/india", response_class=HTMLResponse)
async def india_partial(request: Request, category: str = "", limit: int = 20):
    events = await get_events_for_india(category=category, limit=limit)
    return templates.TemplateResponse("partials/india_panel.html", {
        "request": request,
        "events": events,
        "active_tab": category or "all",
    })


@router.get("/partials/powers", response_class=HTMLResponse)
async def powers_partial(request: Request, country: str = "us", limit: int = 20):
    events = await get_events_for_power(country, limit=limit)
    return templates.TemplateResponse("partials/powers_panel.html", {
        "request": request,
        "events": events,
        "active_tab": country,
    })


@router.get("/partials/situation", response_class=HTMLResponse)
async def situation_partial(request: Request):
    """Lazy-loaded situation board with flashpoint data."""
    flashpoints = await compute_all_flashpoints()
    return templates.TemplateResponse("partials/situation_panel.html", {
        "request": request,
        "flashpoints": flashpoints,
    })


@router.get("/partials/search", response_class=HTMLResponse)
async def search_partial(request: Request, q: str = ""):
    if not q or len(q) < 2:
        return HTMLResponse("<p class='muted'>Type at least 2 characters to search.</p>")
    events = await search_events(q, limit=50)
    return templates.TemplateResponse("partials/feed_panel.html", {
        "request": request,
        "events": events,
        "active_region": "search",
    })


@router.post("/events/{event_id}/read", response_class=HTMLResponse)
async def mark_read(event_id: int):
    await toggle_read(event_id)
    return HTMLResponse("")


@router.post("/events/{event_id}/pin", response_class=HTMLResponse)
async def pin_event(event_id: int):
    await toggle_pin(event_id)
    return HTMLResponse("")
