import logging
import time
import httpx
from datetime import datetime, timezone, timedelta
from app.config import ACLED_EMAIL, ACLED_PASSWORD, get_httpx_kwargs, COUNTRY_REGION_MAP
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.acled")

ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_API = "https://acleddata.com/api/acled/read"

# Token cache (refreshed automatically when expired)
_token_cache = {"access_token": "", "expires_at": 0.0}


async def _get_access_token(client: httpx.AsyncClient) -> str:
    """Obtain or reuse an OAuth access token from ACLED."""
    # Return cached token if still valid (with 5-min buffer)
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 300:
        return _token_cache["access_token"]

    logger.info("Requesting new ACLED OAuth token")
    resp = await client.post(ACLED_TOKEN_URL, data={
        "username": ACLED_EMAIL,
        "password": ACLED_PASSWORD,
        "grant_type": "password",
        "client_id": "acled",
    })
    resp.raise_for_status()
    data = resp.json()

    token = data["access_token"]
    expires_in = data.get("expires_in", 86400)  # Default 24h

    _token_cache["access_token"] = token
    _token_cache["expires_at"] = time.time() + expires_in

    logger.info(f"ACLED token obtained, expires in {expires_in}s")
    return token


async def collect_acled():
    """Fetch conflict events from ACLED API using OAuth auth."""
    if not ACLED_EMAIL or not ACLED_PASSWORD:
        logger.warning("ACLED credentials not configured, skipping")
        return 0

    logger.info("Collecting ACLED events")

    try:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        kwargs = get_httpx_kwargs()
        async with httpx.AsyncClient(**kwargs) as client:
            # Get OAuth token
            token = await _get_access_token(client)

            # Query ACLED API with Bearer token in headers
            headers = {
                "User-Agent": kwargs.get("headers", {}).get("User-Agent", ""),
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            resp = await client.get(ACLED_API, params={
                "_format": "json",
                "event_date": f"{since}|{today}",
                "event_date_where": "BETWEEN",
                "limit": "200",
            }, headers=headers)

            if resp.status_code == 403:
                logger.warning(
                    "ACLED returned 403 — you must accept Terms of Use "
                    "at https://acleddata.com (log in → dashboard → Terms of Use → accept). "
                    "Trying cookie-based auth as fallback..."
                )
                login_resp = await client.post(
                    "https://acleddata.com/user/login?_format=json",
                    json={"name": ACLED_EMAIL, "pass": ACLED_PASSWORD},
                    headers={"Content-Type": "application/json"},
                )
                if login_resp.status_code == 200:
                    # Retry with session cookies
                    resp = await client.get(ACLED_API, params={
                        "_format": "json",
                        "event_date": f"{since}|{today}",
                        "event_date_where": "BETWEEN",
                        "limit": "200",
                    })

            resp.raise_for_status()
            data = resp.json()

        events = data.get("data", [])
        inserted = 0

        for item in events:
            event_type = item.get("event_type", "")
            sub_type = item.get("sub_event_type", "")
            country = item.get("country", "")
            actor1 = item.get("actor1", "")
            notes = item.get("notes", "")

            title = f"{event_type}: {sub_type} in {item.get('admin1', country)}"
            if actor1:
                title = f"{actor1} — {title}"

            lat = item.get("latitude")
            lon = item.get("longitude")
            fatalities = int(item.get("fatalities", 0) or 0)

            # Map ACLED event types to rough Goldstein scores
            goldstein_map = {
                "Battles": -8,
                "Explosions/Remote violence": -9,
                "Violence against civilians": -9,
                "Riots": -5,
                "Protests": -3,
                "Strategic developments": -2,
            }
            goldstein = goldstein_map.get(event_type, -3)

            event = {
                "title": title,
                "summary": notes[:2000] if notes else "",
                "url": "",
                "source": f"ACLED ({item.get('source', 'unknown')})",
                "source_type": "acled",
                "region": COUNTRY_REGION_MAP.get(country, ""),
                "goldstein": goldstein,
                "lat": float(lat) if lat else None,
                "lon": float(lon) if lon else None,
                "fatalities": fatalities,
            }

            event = classify_event(event)
            result = await insert_event(event)
            if result:
                inserted += 1

        logger.info(f"ACLED: inserted {inserted} new events")
        return inserted

    except Exception as e:
        logger.error(f"ACLED collection failed: {e}")
        return 0
