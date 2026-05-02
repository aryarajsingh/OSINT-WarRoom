import logging
import httpx
from app.config import FIRMS_MAP_KEY, get_httpx_kwargs, FLASHPOINTS
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.firms")

FIRMS_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Bounding boxes for conflict zones (W, S, E, N)
CONFLICT_ZONES = {
    "Middle East": "-10,10,65,45",
    "South Asia": "60,5,100,40",
    "South China Sea": "100,0,130,25",
    "Eastern Europe": "20,40,50,60",
    "Korean Peninsula": "120,33,135,43",
}

# Map zone names to our region taxonomy
ZONE_REGION = {
    "Middle East": "middle_east",
    "South Asia": "india",
    "South China Sea": "asia_pacific",
    "Eastern Europe": "europe",
    "Korean Peninsula": "asia_pacific",
}


async def collect_firms():
    """Fetch thermal anomalies from NASA FIRMS in conflict zones."""
    if not FIRMS_MAP_KEY:
        logger.warning("FIRMS MAP_KEY not configured, skipping")
        return 0

    logger.info("Collecting FIRMS thermal data")
    total_inserted = 0

    for zone_name, bbox in CONFLICT_ZONES.items():
        try:
            # VIIRS SNPP, last 24 hours
            url = f"{FIRMS_API}/{FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/{bbox}/1"

            kwargs = get_httpx_kwargs()
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            lines = resp.text.strip().split("\n")
            if len(lines) <= 1:
                continue

            # Parse CSV: latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
            headers = lines[0].split(",")
            lat_idx = headers.index("latitude") if "latitude" in headers else 0
            lon_idx = headers.index("longitude") if "longitude" in headers else 1
            conf_idx = headers.index("confidence") if "confidence" in headers else -1
            frp_idx = headers.index("frp") if "frp" in headers else -1
            date_idx = headers.index("acq_date") if "acq_date" in headers else -1

            # Only high-confidence detections with significant fire radiative power
            for line in lines[1:]:
                fields = line.split(",")
                if len(fields) < max(lat_idx, lon_idx, conf_idx) + 1:
                    continue

                try:
                    lat = float(fields[lat_idx])
                    lon = float(fields[lon_idx])
                    confidence = fields[conf_idx] if conf_idx >= 0 else "nominal"
                    frp = float(fields[frp_idx]) if frp_idx >= 0 and fields[frp_idx] else 0

                    # Only significant thermal anomalies (FRP > 10 MW or high confidence)
                    if confidence not in ("high", "h") and frp < 10:
                        continue

                    acq_date = fields[date_idx] if date_idx >= 0 else ""

                    event = {
                        "title": f"Thermal anomaly detected in {zone_name} (FRP: {frp:.0f} MW)",
                        "summary": f"VIIRS satellite detected thermal hotspot at {lat:.3f}, {lon:.3f}. Confidence: {confidence}. Fire Radiative Power: {frp:.0f} MW.",
                        "url": f"https://firms.modaps.eosdis.nasa.gov/map/#d:today;@{lon},{lat},10z",
                        "source": "NASA FIRMS",
                        "source_type": "firms",
                        "region": ZONE_REGION.get(zone_name, ""),
                        "lat": lat,
                        "lon": lon,
                        "goldstein": -7,  # Thermal in conflict zone = significant
                    }

                    event = classify_event(event)
                    result = await insert_event(event)
                    if result:
                        total_inserted += 1

                except (ValueError, IndexError):
                    continue

        except Exception as e:
            logger.warning(f"FIRMS {zone_name} failed: {e}")
            continue

    logger.info(f"FIRMS: inserted {total_inserted} new thermal events")
    return total_inserted
