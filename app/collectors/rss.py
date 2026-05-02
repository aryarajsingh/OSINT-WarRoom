import asyncio
import logging
import yaml
import feedparser
import httpx
from datetime import datetime, timezone
from app.config import FEEDS_PATH, get_httpx_kwargs, get_jitter
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.rss")


async def load_feeds() -> dict:
    """Load feed configuration from feeds.yml."""
    with open(FEEDS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    feeds = {"hot": [], "warm": []}
    for group_name, feed_list in data.items():
        if not isinstance(feed_list, list):
            continue
        for feed in feed_list:
            tier = feed.get("tier", "warm")
            feeds[tier].append(feed)

    logger.info(f"Loaded {len(feeds['hot'])} hot feeds, {len(feeds['warm'])} warm feeds")
    return feeds


async def fetch_feed(feed_config: dict) -> list[dict]:
    """Fetch and parse a single RSS feed."""
    url = feed_config["url"]
    name = feed_config.get("name", url)
    region = feed_config.get("region", "")
    category = feed_config.get("category", "")

    try:
        kwargs = get_httpx_kwargs()
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        parsed = feedparser.parse(resp.text)
        events = []

        for entry in parsed.entries[:15]:  # Max 15 per feed per cycle
            title = entry.get("title", "").strip()
            if not title:
                continue

            link = entry.get("link", "")
            summary = entry.get("summary", entry.get("description", ""))
            # Strip HTML from summary
            if summary:
                from html import unescape
                import re
                summary = re.sub(r'<[^>]+>', '', unescape(summary))[:300]

            # Extract image if available (check thumbnail first — most common)
            image_url = ""
            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get("url", "")
            elif hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url", "")
            elif hasattr(entry, "enclosures") and entry.enclosures:
                for enc in entry.enclosures:
                    if "image" in enc.get("type", ""):
                        image_url = enc.get("href", "")
                        break

            event = {
                "title": title,
                "summary": summary,
                "url": link,
                "source": name,
                "source_type": "rss",
                "region": region,
                "category": category,
                "image_url": image_url,
            }

            event = classify_event(event)
            events.append(event)

        return events

    except Exception as e:
        logger.warning(f"Failed to fetch {name}: {e}")
        return []


async def collect_feeds(tier: str, feeds: dict):
    """Collect all feeds for a given tier."""
    feed_list = feeds.get(tier, [])
    if not feed_list:
        return

    logger.info(f"Collecting {len(feed_list)} {tier} feeds")

    # Stagger requests 1-3 seconds apart
    inserted = 0
    for feed_config in feed_list:
        events = await fetch_feed(feed_config)
        for event in events:
            result = await insert_event(event)
            if result:
                inserted += 1

        # Anti-fingerprinting: stagger between feeds
        await asyncio.sleep(1 + abs(get_jitter()) / 30)

    logger.info(f"RSS {tier}: inserted {inserted} new events")
    return inserted
