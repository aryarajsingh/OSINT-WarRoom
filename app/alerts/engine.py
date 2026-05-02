import asyncio
import logging
import time
from datetime import datetime, timezone
from collections import defaultdict
from app.alerts.telegram import send_text, send_photo, send_location, format_alert
from app.routes.sse import broadcast_event, broadcast_alert

logger = logging.getLogger("warroom.alerts")

# Batching queues for different priority levels
_batches: dict[str, list[dict]] = defaultdict(list)
_batch_lock = asyncio.Lock()

# Boot suppression: no Telegram alerts for first 3 minutes after startup
_boot_time = time.time()
BOOT_SUPPRESS_SECONDS = 180  # 3 minutes


def _is_boot_phase() -> bool:
    """Are we still in the initial data fetch window?"""
    return (time.time() - _boot_time) < BOOT_SUPPRESS_SECONDS


def _is_fresh_enough(event: dict, max_age_seconds: int) -> bool:
    """Check if event was created recently enough to warrant an alert.
    During normal operation, events are inserted near real-time,
    so created_at is always recent. This mostly catches old articles
    from the initial RSS crawl."""
    created = event.get("created_at")
    if not created:
        return True  # No timestamp = probably just inserted = fresh

    try:
        # SQLite datetime format
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        # If naive (no timezone), assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age < max_age_seconds
    except Exception:
        return True  # Parse error = assume fresh


async def process_event_alert(event: dict):
    """Process an event through the alert engine.

    RULES:
    - During boot (first 3 min): SSE only, NO Telegram
    - CRITICAL: instant Telegram IF fresh (< 60 min)
    - HIGH: batched Telegram every 5 min IF fresh (< 6 hours)
    - MEDIUM/LOW: dashboard/SSE only, no Telegram
    """
    priority = event.get("priority", "low")
    source_type = event.get("source_type", "")

    # Map-only data (ADS-B, FIRMS, USGS): skip feed SSE + Telegram entirely
    # These events still go to DB (map + situation board use them)
    from app.config import MAP_ONLY_SOURCE_TYPES
    if source_type in MAP_ONLY_SOURCE_TYPES:
        return

    # Broadcast to dashboard feed via SSE
    event_html = _render_event_html(event)
    broadcast_event(event_html)

    # Historical data sources: NEVER send Telegram (dashboard + SSE only)
    if source_type in ("ucdp",):
        return

    # During boot phase: suppress ALL Telegram notifications
    if _is_boot_phase():
        return

    if priority == "critical":
        # Only send if event is genuinely fresh (< 60 min)
        if _is_fresh_enough(event, max_age_seconds=3600):
            await _send_critical_alert(event)
            alert_html = f'<strong style="color:#ff3344;">{event["title"][:120]}</strong>'
            broadcast_alert(alert_html)
        else:
            logger.debug(f"Skipping stale CRITICAL alert: {event['title'][:60]}")

    elif priority == "high":
        # Only batch if fresh (< 6 hours)
        if _is_fresh_enough(event, max_age_seconds=21600):
            async with _batch_lock:
                _batches["high"].append(event)


async def _send_critical_alert(event: dict):
    """Send a critical alert immediately to Telegram."""
    message = format_alert(event)
    await send_text(message)

    # Send photo if available
    if event.get("image_url"):
        await send_photo(event["image_url"], caption=event["title"][:200])

    # Send location pin if coordinates available
    if event.get("lat") and event.get("lon"):
        await send_location(event["lat"], event["lon"])

    logger.warning(f"CRITICAL ALERT sent: {event['title'][:80]}")


async def flush_high_batch():
    """Send batched HIGH priority alerts to Telegram as rich messages."""
    # Don't flush during boot phase
    if _is_boot_phase():
        return

    async with _batch_lock:
        events = _batches["high"][:]
        _batches["high"].clear()

    if not events:
        return

    # Send each event as a full rich message (same format as CRITICAL)
    for e in events[:10]:  # Max 10 per batch to avoid spam
        message = format_alert(e)
        await send_text(message)

        # Send image if available
        if e.get("image_url"):
            caption = e.get("title", "")[:200]
            await send_photo(e["image_url"], caption=caption)

    if len(events) > 10:
        await send_text(f"\U0001f4cb +{len(events) - 10} more HIGH priority events on dashboard")

    logger.info(f"Flushed {len(events)} HIGH alerts")


async def flush_medium_batch():
    """Medium priority: no Telegram, just log for transparency."""
    # Medium events stay on dashboard only — no phone notifications
    pass


def _render_event_html(event: dict) -> str:
    """Render a minimal HTML event card for SSE broadcast."""
    priority = event.get("priority", "low")
    tier = event.get("source_tier", "UNKNOWN").lower()
    title = event.get("title", "")
    source = event.get("source", "")
    url = event.get("url", "")
    region = event.get("region", "")
    created = event.get("created_at", "")

    return f"""<article class="event-card unread priority-{priority}" data-region="{region}" data-priority="{priority}" style="animation: fadeIn 0.3s ease;">
    <div class="priority-bar priority-bg-{priority}"></div>
    <div class="event-content">
        <div class="event-meta">
            <span class="source-badge tier-{tier}">{event.get("source_tier", "")}</span>
            <span class="source-name">{source}</span>
            <span class="event-time" data-time="{created}">just now</span>
        </div>
        <h3 class="event-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
        <div class="event-tags">
            {"<span class='tag tag-region'>" + region + "</span>" if region else ""}
        </div>
    </div>
</article>"""
