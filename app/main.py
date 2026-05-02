import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import STATIC_DIR, RETENTION_DAYS
from app.database import get_db, close_db, prune_old_events
from app.collectors.rss import load_feeds, collect_feeds
from app.collectors.gdelt import collect_gdelt
from app.collectors.acled import collect_acled
from app.collectors.firms import collect_firms
from app.collectors.usgs import collect_usgs
from app.collectors.adsb import collect_adsb
from app.collectors.ucdp import collect_ucdp
from app.collectors.telegram_channels import collect_telegram_channels
from app.collectors.gdelt_geo import collect_gdelt_geo
from app.alerts.engine import flush_high_batch, flush_medium_batch
from app.routes import dashboard, partials, sse, api

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("warroom")

scheduler = AsyncIOScheduler()
_feeds = {}


async def initial_fetch():
    """Immediate data fetch on startup — don't wait for scheduler intervals."""
    global _feeds
    logger.info("Starting initial data fetch...")

    _feeds = await load_feeds()

    # Fire all collectors once with staggered start
    tasks = [
        collect_feeds("hot", _feeds),
        collect_feeds("warm", _feeds),
        collect_gdelt(),
        collect_gdelt_geo(),
        collect_usgs(),
        collect_telegram_channels(),
    ]

    # Run RSS + GDELT + USGS + Telegram in parallel (these are safe)
    await asyncio.gather(*tasks, return_exceptions=True)

    # Rate-limited APIs — run sequentially
    await collect_acled()
    await collect_ucdp()
    await collect_firms()
    await collect_adsb()

    logger.info("Initial fetch complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await get_db()
    logger.info("Database initialized")

    # Immediate data fetch
    asyncio.create_task(initial_fetch())

    # Schedule collectors with tiered polling
    # Hot tier: 2 minutes
    scheduler.add_job(
        collect_feeds, "interval", minutes=2,
        args=["hot", _feeds], id="rss_hot", replace_existing=True,
    )
    scheduler.add_job(
        collect_telegram_channels, "interval", minutes=2,
        id="telegram", replace_existing=True,
    )

    # Warm tier: 10 minutes
    scheduler.add_job(
        collect_feeds, "interval", minutes=10,
        args=["warm", _feeds], id="rss_warm", replace_existing=True,
    )

    # Standard tier: 15 minutes
    scheduler.add_job(
        collect_gdelt, "interval", minutes=15,
        id="gdelt", replace_existing=True,
    )
    scheduler.add_job(
        collect_gdelt_geo, "interval", minutes=30,
        id="gdelt_geo", replace_existing=True,
    )

    # Slow tier: 30-60 minutes
    scheduler.add_job(
        collect_usgs, "interval", minutes=30,
        id="usgs", replace_existing=True,
    )
    scheduler.add_job(
        collect_acled, "interval", minutes=60,
        id="acled", replace_existing=True,
    )
    scheduler.add_job(
        collect_ucdp, "interval", hours=6,
        id="ucdp", replace_existing=True,
    )
    scheduler.add_job(
        collect_firms, "interval", minutes=60,
        id="firms", replace_existing=True,
    )
    scheduler.add_job(
        collect_adsb, "interval", minutes=5,
        id="adsb", replace_existing=True,
    )

    # Alert batch flushers
    scheduler.add_job(
        flush_high_batch, "interval", minutes=1,
        id="flush_high", replace_existing=True,
    )
    scheduler.add_job(
        flush_medium_batch, "interval", minutes=15,
        id="flush_medium", replace_existing=True,
    )

    # Data retention cleanup
    scheduler.add_job(
        prune_old_events, "interval", hours=24,
        args=[RETENTION_DAYS], id="prune", replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with tiered polling")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    await close_db()
    logger.info("Shutdown complete")


# Create app
app = FastAPI(title="OSINT War Room", lifespan=lifespan)

# Security headers middleware
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' https://*.basemaps.cartocdn.com https://t.me https://*.eosdis.nasa.gov data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-src 'none'; "
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include routers
app.include_router(dashboard.router)
app.include_router(partials.router)
app.include_router(sse.router)
app.include_router(api.router)
