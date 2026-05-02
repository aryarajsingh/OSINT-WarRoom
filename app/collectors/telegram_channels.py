import logging
import re
import httpx
from bs4 import BeautifulSoup
from app.config import get_httpx_kwargs
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.telegram")

# Public OSINT Telegram channels (web preview only, no account needed)
# Only channels with working t.me/s/ web preview (validated March 2026)
CHANNELS = [
    # --- Global / Multi-region OSINT ---
    {"username": "AuroraIntel", "name": "Aurora Intel"},
    {"username": "BNONews", "name": "BNO News"},
    {"username": "OSINTdefender", "name": "OSINTdefender"},
    {"username": "CIG_telegram", "name": "Conflict Intelligence"},
    {"username": "inikiforov", "name": "Intel Republic"},
    {"username": "WarMonitors", "name": "War Monitors"},
    {"username": "MilitaryBrief", "name": "Military Brief"},
    # --- Europe / Russia-Ukraine ---
    {"username": "liveuamap", "name": "Liveuamap"},
    {"username": "Flash_news_ua", "name": "Flash News"},
    {"username": "nexta_live", "name": "NEXTA Live"},
    {"username": "TheDeadDistrict", "name": "The Dead District"},
    # --- Middle East ---
    {"username": "Middle_East_Spectator", "name": "Middle East Spectator"},
    {"username": "MENAUpdates", "name": "MENA Updates"},
    # --- Asia-Pacific ---
    {"username": "SouthChinaSeaNews", "name": "SCS Probing Initiative"},
    # --- India ---
    {"username": "indiandefencenews", "name": "India Defence News"},
]

# Lightweight relevance signal words — if NONE match, skip the message.
# Intentionally broad: the downstream classifier handles precision.
RELEVANCE_SIGNALS = frozenset({
    # Conflict / military
    "military", "army", "navy", "air force", "troops", "soldiers",
    "strike", "attack", "missile", "rocket", "drone", "bomb",
    "killed", "casualties", "dead", "wounded", "explosion",
    "war", "conflict", "combat", "battle", "fighting", "clashes",
    "airstrike", "shelling", "artillery", "tank", "infantry",
    # Geopolitical
    "sanctions", "nato", "nuclear", "ceasefire", "diplomacy", "treaty",
    "border", "invasion", "occupied", "blockade", "embargo",
    "president", "minister", "government", "parliament", "summit",
    "coup", "martial law", "state of emergency",
    # Intelligence / OSINT
    "breaking", "confirmed", "reports", "alert", "warning",
    "intercepted", "intelligence", "surveillance", "satellite",
    # Weapons systems
    "icbm", "submarine", "carrier", "destroyer", "fighter",
    "radar", "defense", "defence", "warship", "frigate",
    # Key regions / actors
    "ukraine", "russia", "china", "taiwan", "israel", "iran",
    "gaza", "syria", "korea", "india", "pakistan",
    "pentagon", "kremlin", "beijing", "tehran",
    "hamas", "hezbollah", "houthi", "wagner",
    "sudan", "ethiopia", "somalia", "sahel",
})


def _has_relevance_signal(text: str) -> bool:
    """Fast check: does the message contain ANY conflict/geopolitical signal word?"""
    text_lower = text.lower()
    return any(word in text_lower for word in RELEVANCE_SIGNALS)


async def collect_telegram_channels():
    """Fetch posts from public Telegram channel web previews."""
    logger.info(f"Collecting from {len(CHANNELS)} Telegram channels")
    total_inserted = 0

    for channel in CHANNELS:
        try:
            url = f"https://t.me/s/{channel['username']}"
            kwargs = get_httpx_kwargs()

            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(url)

                # If we get redirected away from /s/ URL, the channel doesn't support web preview
                if resp.status_code in (301, 302) or "/s/" not in str(resp.url):
                    logger.debug(f"Telegram {channel['name']}: no web preview available")
                    continue

                if resp.status_code != 200:
                    logger.debug(f"Telegram {channel['name']}: HTTP {resp.status_code}")
                    continue

            soup = BeautifulSoup(resp.text, "lxml")

            # Telegram web preview uses .tgme_widget_message class
            messages = soup.find_all("div", class_="tgme_widget_message")

            if not messages:
                logger.debug(f"Telegram {channel['name']}: no messages found in HTML")
                continue

            for msg in messages[-10:]:  # Last 10 messages
                # Extract text
                text_div = msg.find("div", class_="tgme_widget_message_text")
                if not text_div:
                    continue

                text = text_div.get_text(strip=True)
                if not text or len(text) < 20:
                    continue

                # Relevance gate: skip messages with zero geopolitical signal
                if not _has_relevance_signal(text):
                    continue

                # Extract message link
                msg_link = ""
                link_tag = msg.find("a", class_="tgme_widget_message_date")
                if link_tag:
                    msg_link = link_tag.get("href", "")

                # Extract image
                image_url = ""
                photo_wrap = msg.find("a", class_="tgme_widget_message_photo_wrap")
                if photo_wrap:
                    style = photo_wrap.get("style", "")
                    img_match = re.search(r"url\('(.+?)'\)", style)
                    if img_match:
                        image_url = img_match.group(1)

                # Extract video thumbnail
                if not image_url:
                    video_thumb = msg.find("i", class_="tgme_widget_message_video_thumb")
                    if video_thumb:
                        style = video_thumb.get("style", "")
                        img_match = re.search(r"url\('(.+?)'\)", style)
                        if img_match:
                            image_url = img_match.group(1)

                # Title: first line (generous limit)
                title = text.split("\n")[0][:500]

                event = {
                    "title": title,
                    "summary": text[:2000],
                    "url": msg_link,
                    "source": channel["name"],
                    "source_type": "telegram",
                    "image_url": image_url,
                }

                event = classify_event(event)
                result = await insert_event(event)
                if result:
                    total_inserted += 1

        except Exception as e:
            logger.warning(f"Telegram {channel['name']} failed: {e}")
            continue

    logger.info(f"Telegram: inserted {total_inserted} new posts")
    return total_inserted
