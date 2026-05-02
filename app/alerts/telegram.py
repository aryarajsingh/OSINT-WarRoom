import logging
import httpx
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, get_httpx_kwargs

logger = logging.getLogger("warroom.telegram_bot")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


async def send_text(message: str, parse_mode: str = "HTML"):
    """Send a text message to the configured Telegram chat."""
    if not _enabled():
        return

    try:
        # Telegram max message length is 4096 chars
        if len(message) > 4096:
            message = message[:4090] + "\n…"
        kwargs = get_httpx_kwargs()
        async with httpx.AsyncClient(**kwargs) as client:
            await client.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False,
            })
    except Exception as e:
        logger.error(f"Telegram send_text failed: {e}")


async def send_photo(photo_url: str, caption: str = ""):
    """Send a photo from URL to the configured Telegram chat."""
    if not _enabled():
        return

    try:
        kwargs = get_httpx_kwargs()
        async with httpx.AsyncClient(**kwargs) as client:
            await client.post(f"{TELEGRAM_API}/sendPhoto", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": caption[:1024],
                "parse_mode": "HTML",
            })
    except Exception as e:
        logger.error(f"Telegram send_photo failed: {e}")


async def send_location(lat: float, lon: float):
    """Send a location pin to the configured Telegram chat."""
    if not _enabled():
        return

    try:
        kwargs = get_httpx_kwargs()
        async with httpx.AsyncClient(**kwargs) as client:
            await client.post(f"{TELEGRAM_API}/sendLocation", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "latitude": lat,
                "longitude": lon,
            })
    except Exception as e:
        logger.error(f"Telegram send_location failed: {e}")


def format_alert(event: dict) -> str:
    """Format an event into a Telegram-friendly alert message."""
    priority = event.get("priority", "low").upper()
    title = event.get("title", "Unknown event")
    source = event.get("source", "Unknown")
    region = event.get("region", "")
    flashpoint = event.get("flashpoint", "")
    url = event.get("url", "")
    goldstein = event.get("goldstein")
    summary = event.get("summary", "")

    # Priority emoji
    emoji_map = {
        "CRITICAL": "\U0001f534",  # red circle
        "HIGH": "\U0001f7e0",      # orange circle
        "MEDIUM": "\U0001f7e1",    # yellow circle
        "LOW": "\U0001f7e2",       # green circle
    }
    emoji = emoji_map.get(priority, "")

    lines = [
        f"{emoji} <b>{priority} PRIORITY</b>",
        "",
        f"<b>{title}</b>",
    ]

    # Only show summary if it adds information beyond the title
    if summary and summary.strip() != title.strip() and not summary.strip().startswith(title.strip()):
        lines.append(f"\n{summary}")

    lines.append("")
    lines.append(f"Source: {source}")

    if region:
        lines.append(f"Region: {region}")
    if flashpoint:
        lines.append(f"Flashpoint: {flashpoint}")
    if goldstein is not None:
        lines.append(f"Goldstein: {goldstein:.1f}")
    if url:
        lines.append(f'\n<a href="{url}">Source Link</a>')

    return "\n".join(lines)
