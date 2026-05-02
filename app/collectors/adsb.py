import logging
import httpx
from app.config import get_httpx_kwargs
from app.database import insert_event
from app.processing.classifier import classify_event

logger = logging.getLogger("warroom.adsb")

# Free ADS-B data sources with military endpoints (ADSBx v2 compatible)
# These are community-run, no auth needed, 1 req/sec rate limit
ADSB_SOURCES = [
    {"name": "Airplanes.live", "url": "https://api.airplanes.live/v2/mil"},
    {"name": "ADSB.one", "url": "https://api.adsb.one/v2/mil/"},
    {"name": "adsb.fi", "url": "https://opendata.adsb.fi/api/v2/mil"},
]

# Known interesting military aircraft types
INTERESTING_TYPES = {
    "RC135": "Signals Intelligence (RC-135 Rivet Joint)",
    "E3": "AWACS (E-3 Sentry)",
    "E6": "Nuclear Command (E-6B Mercury)",
    "P8": "Maritime Patrol (P-8A Poseidon)",
    "KC135": "Air Refueling (KC-135)",
    "KC46": "Air Refueling (KC-46A)",
    "B52": "Strategic Bomber (B-52)",
    "B1": "Strategic Bomber (B-1B Lancer)",
    "B2": "Stealth Bomber (B-2 Spirit)",
    "B21": "Stealth Bomber (B-21 Raider)",
    "C17": "Strategic Airlift (C-17)",
    "C5": "Strategic Airlift (C-5M Galaxy)",
    "RQ4": "Surveillance Drone (RQ-4 Global Hawk)",
    "MQ9": "Combat Drone (MQ-9 Reaper)",
    "FORTE": "Surveillance (RQ-4 FORTE)",
    "E8": "Ground Surveillance (E-8C JSTARS)",
    "KC10": "Air Refueling (KC-10 Extender)",
    "F35": "Stealth Fighter (F-35)",
    "F22": "Air Superiority (F-22 Raptor)",
    "F15": "Strike Fighter (F-15)",
    "F16": "Multirole Fighter (F-16)",
    "A10": "Close Air Support (A-10 Warthog)",
    "EP3": "SIGINT (EP-3E Aries)",
    "P3": "Maritime Patrol (P-3 Orion)",
    "DUKE": "Special Ops (MC-12W)",
    "HOMER": "Surveillance (unknown mission)",
}


async def collect_adsb():
    """Fetch military aircraft positions from free ADS-B APIs.
    Tries multiple sources with automatic fallback."""
    logger.info("Collecting ADS-B military flights")

    for source in ADSB_SOURCES:
        try:
            kwargs = get_httpx_kwargs()
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(
                    source["url"],
                    headers={"Accept": "application/json"},
                    timeout=15.0,
                )

            if resp.status_code != 200:
                logger.warning(f"ADS-B {source['name']} returned {resp.status_code}")
                continue

            data = resp.json()
            aircraft_list = data.get("ac", [])

            if not aircraft_list:
                logger.info(f"ADS-B {source['name']}: no military aircraft in response")
                continue

            logger.info(
                f"ADS-B {source['name']}: received {len(aircraft_list)} military aircraft"
            )
            return await _process_aircraft(aircraft_list, source["name"])

        except httpx.ConnectTimeout:
            logger.warning(f"ADS-B {source['name']} timeout, trying next source")
            continue
        except httpx.ConnectError:
            logger.warning(f"ADS-B {source['name']} connection error, trying next source")
            continue
        except Exception as e:
            logger.warning(
                f"ADS-B {source['name']} failed: {type(e).__name__}: {e}"
            )
            continue

    logger.warning("All ADS-B sources failed")
    return 0


async def _process_aircraft(aircraft_list: list, source_name: str) -> int:
    """Process the aircraft list and insert interesting ones as events."""
    inserted = 0

    for ac in aircraft_list:
        # dbFlags & 1 = military in the v2 API format
        db_flags = ac.get("dbFlags", 0) or 0
        is_mil = db_flags & 1 if isinstance(db_flags, int) else True

        if not is_mil:
            continue

        callsign = (ac.get("flight", "") or "").strip()
        if not callsign:
            continue

        lat = ac.get("lat")
        lon = ac.get("lon")
        alt = ac.get("alt_baro", ac.get("alt_geom", 0))
        ac_type = (ac.get("t", "") or "").strip()
        reg = (ac.get("r", "") or "").strip()
        hex_code = (ac.get("hex", "") or "").strip()

        if lat is None or lon is None:
            continue

        # Identify interesting aircraft types
        # Match against aircraft TYPE CODE (exact or prefix) — not callsign
        # to avoid false positives like "FAB2590" matching "B2"
        description = ""
        ac_type_upper = ac_type.upper()
        callsign_upper = callsign.upper()

        for prefix, desc in INTERESTING_TYPES.items():
            # Check type code (e.g. "C17" == "C17", "B52H" starts with "B52")
            if ac_type_upper and (
                ac_type_upper == prefix or ac_type_upper.startswith(prefix)
            ):
                description = desc
                break
            # For callsigns, only match at start (e.g. "FORTE11" starts with "FORTE")
            if callsign_upper.startswith(prefix):
                description = desc
                break

        if not description:
            description = f"Military aircraft ({ac_type or 'unknown type'})"

        title = f"Military flight: {callsign} — {description}"

        # Higher Goldstein for ISR/bomber/nuclear command aircraft
        goldstein = -2  # Default: military presence
        high_value_types = ("RC135", "E6", "B52", "B1B", "B2", "B21", "RQ4", "MQ9", "E8")
        high_value_callsigns = ("FORTE", "HOMER", "DUKE", "JAKE")
        if ac_type_upper and any(
            ac_type_upper == t or ac_type_upper.startswith(t)
            for t in high_value_types
        ):
            goldstein = -5
        elif any(callsign_upper.startswith(c) for c in high_value_callsigns):
            goldstein = -5

        event = {
            "title": title,
            "summary": (
                f"Callsign: {callsign}, Type: {ac_type}, "
                f"Reg: {reg}, Alt: {alt}ft"
            ),
            "url": f"https://globe.adsbexchange.com/?icao={hex_code}",
            "source": f"ADS-B ({source_name})",
            "source_type": "adsb",
            "lat": float(lat),
            "lon": float(lon),
            "goldstein": goldstein,
        }

        event = classify_event(event)
        result = await insert_event(event)
        if result:
            inserted += 1

    logger.info(f"ADS-B: inserted {inserted} military flights")
    return inserted
