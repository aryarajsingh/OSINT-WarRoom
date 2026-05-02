import hashlib
import math
import re
from app.config import (
    REGION_KEYWORDS, FLASHPOINTS, SOURCE_TIERS, SOURCE_TYPE_TIER_FALLBACK,
)
from app.models import Priority, SourceTier


def _word_match(keyword: str, text: str) -> bool:
    """Check if keyword appears as a whole word/phrase in text."""
    return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE))


# ===================================================================
# PRIORITY SCORING SYSTEM
#
# Your phone buzzes for things HAPPENING, not things written about.
#
# Score components:
#   SOURCE WEIGHT   (0-25)  — Wire/OSINT Telegram = breaking, think tank = not
#   ACTION SIGNAL   (0-40)  — Active strikes/attacks vs. policy papers
#   SEVERITY        (0-20)  — Goldstein + fatalities
#   CONTEXT BOOST   (0-15)  — India defence, active flashpoint
#   DAMPENER        (0 to -20) — Analysis/opinion/report = NOT breaking
#
# Thresholds:
#   >= 70  CRITICAL  — instant Telegram
#   >= 45  HIGH      — 5-min batch Telegram
#   >= 25  MEDIUM    — 30-min digest or dashboard
#   <  25  LOW       — dashboard only
# ===================================================================

# Things ACTIVELY HAPPENING (high signal)
ACTION_KEYWORDS = [
    "strikes", "struck", "attacked", "launched", "shelling",
    "explosion", "blast", "detonation", "intercept",
    "killed", "casualties", "death toll",
    "invaded", "incursion", "breached",
    "shot down", "downed", "sunk",
    "breaking", "just in", "developing", "happening now",
    "confirmed dead", "reports of", "underway",
    "fired upon", "missile launch", "rocket attack",
    "air raid", "bombardment", "carpet bomb",
    "declared war", "martial law", "state of emergency",
    "ceasefire violated", "ceasefire collapsed",
    # Additional high-signal action terms
    "ambush", "raid", "hostage", "kidnapped", "abducted",
    "siege", "assassination", "assassinated",
    "coup", "overthrown", "hijacked",
    "targeted killing", "neutralized",
    "stormed", "overrun", "captured",
    "car bomb", "suicide bomb", "ied",
    "mass shooting", "massacre",
]

# Escalation signals (not immediate but serious)
ESCALATION_KEYWORDS = [
    "deployed", "mobilized", "buildup", "amassing",
    "carrier strike group", "naval blockade", "no-fly zone",
    "nuclear test", "icbm", "thermonuclear",
    "border standoff", "troops massed",
    "evacuate embassy", "recalled ambassador",
    "ultimatum", "threatens retaliation",
    "chemical weapon", "biological weapon",
    # Additional escalation signals
    "article 5", "mutual defense", "war footing",
    "conscription", "general mobilization",
    "defcon", "nuclear alert", "red line crossed",
    "nuclear posture", "strategic deterrent",
    "full mobilization", "war declaration",
    "emergency session", "un security council",
]

# Routine military/geopolitical (not urgent)
DEVELOPMENT_KEYWORDS = [
    "sanctions", "military exercise", "drill", "procurement",
    "arms deal", "missile test", "weapons test", "commissioning",
    "diplomatic talks", "summit", "bilateral",
    "trade war", "tariff",
]

# Analysis/background indicators — these REDUCE urgency
DAMPENER_KEYWORDS = [
    "report", "analysis", "commentary", "opinion", "editorial",
    "perspective", "assessment", "outlook", "review",
    "could", "should", "may impact", "might lead",
    "history of", "looking back", "lessons from",
    "plans to", "budget", "challenges for",
    "fleet size", "upgrade plans", "modernization",
    "why it matters", "how it works", "what it means",
    "q&a", "interview", "podcast", "webinar",
    "explainer", "backgrounder", "timeline of",
]

# India-specific events worth knowing about
INDIA_BOOST_KEYWORDS = [
    "drdo", "brahmos", "tejas", "rafale", "s-400",
    "lac", "line of actual control", "galwan", "pangong", "doklam",
    "indian navy", "indian air force", "ins",
    "isro", "arunachal", "ladakh",
    "border clash", "border incident",
]


def compute_priority_score(text: str, event: dict) -> tuple[int, str]:
    """
    Compute a numeric priority score (0-100) and return (score, reason).
    """
    score = 0
    reasons = []

    source = event.get("source", "").lower()
    source_tier = event.get("source_tier", "UNKNOWN")
    goldstein = event.get("goldstein")
    fatalities = event.get("fatalities", 0) or 0
    region = event.get("region", "")
    flashpoint = event.get("flashpoint", "")
    source_type = event.get("source_type", "")

    # --- 1. SOURCE WEIGHT (0-25) ---
    # OSINT Telegram channels are inherently real-time breaking intel
    if source_type == "telegram":
        score += 22
        reasons.append("telegram_osint")
    elif source_tier == "WIRE":
        score += 20
        reasons.append("wire_service")
    elif source_tier == "GOV":
        score += 12
        reasons.append("gov_source")
    elif source_type == "acled":
        score += 18  # ACLED = structured conflict data
        reasons.append("acled_conflict")
    elif source_type == "ucdp":
        score += 10  # UCDP = historical conflict data, ~1 month lag
        reasons.append("ucdp_historical")
    elif source_type == "firms":
        score += 8  # FIRMS alone is not enough — could be a forest fire
        reasons.append("firms_thermal")
    elif source_tier == "ANALYSIS":
        score += 3  # Think tanks rarely report breaking news
        reasons.append("analysis_source")
    else:
        score += 5

    # --- 2. ACTION SIGNAL (0-40) ---
    action_hits = sum(1 for kw in ACTION_KEYWORDS if _word_match(kw, text))
    if action_hits >= 3:
        score += 40
        reasons.append(f"action_strong({action_hits})")
    elif action_hits >= 2:
        score += 30
        reasons.append(f"action_moderate({action_hits})")
    elif action_hits >= 1:
        score += 18
        reasons.append(f"action_weak({action_hits})")

    escalation_hits = sum(1 for kw in ESCALATION_KEYWORDS if _word_match(kw, text))
    if escalation_hits >= 2:
        score += 25
        reasons.append(f"escalation({escalation_hits})")
    elif escalation_hits >= 1:
        score += 12
        reasons.append(f"escalation_single")

    dev_hits = sum(1 for kw in DEVELOPMENT_KEYWORDS if _word_match(kw, text))
    if dev_hits >= 1 and action_hits == 0:
        score += 8
        reasons.append("development")

    # --- 3. SEVERITY (0-20) ---
    if goldstein is not None:
        if goldstein <= -8:
            score += 20
            reasons.append(f"goldstein_severe({goldstein:.1f})")
        elif goldstein <= -5:
            score += 12
            reasons.append(f"goldstein_high({goldstein:.1f})")
        elif goldstein <= -3:
            score += 5

    if fatalities >= 50:
        score += 25
        reasons.append(f"mass_casualty({fatalities})")
    elif fatalities >= 10:
        score += 15
        reasons.append(f"significant_casualties({fatalities})")
    elif fatalities > 0:
        score += 8
        reasons.append(f"casualties({fatalities})")

    # --- 4. CONTEXT BOOST (0-15) ---
    # India defence events you care about
    if region == "india":
        india_hits = sum(1 for kw in INDIA_BOOST_KEYWORDS if _word_match(kw, text))
        if india_hits >= 2:
            score += 15
            reasons.append(f"india_defence({india_hits})")
        elif india_hits >= 1:
            score += 8
            reasons.append("india_relevant")

    # Active flashpoint boost
    if flashpoint:
        score += 5
        reasons.append(f"flashpoint({flashpoint})")

    # FIRMS + active flashpoint = much more significant
    if source_type == "firms" and flashpoint:
        score += 12
        reasons.append("firms_in_flashpoint")

    # --- 5. DAMPENER (subtract 0-20) ---
    dampener_hits = sum(1 for kw in DAMPENER_KEYWORDS if _word_match(kw, text))
    if dampener_hits >= 3:
        score -= 20
        reasons.append(f"analysis_heavy(-20)")
    elif dampener_hits >= 2:
        score -= 12
        reasons.append(f"analysis_moderate(-12)")
    elif dampener_hits >= 1:
        score -= 5
        reasons.append(f"analysis_light(-5)")

    # USGS seismic events are almost never urgent for geopolitics
    if source_type == "usgs":
        score -= 15
        reasons.append("seismic_dampener")

    # UCDP is historical conflict data (~1 month lag), never breaking news
    # Valuable for situation board scoring but shouldn't trigger alerts
    if source_type == "ucdp":
        score = min(score, 40)  # Cap below HIGH threshold (45)
        reasons.append("ucdp_historical_cap")

    # FIRMS without flashpoint is probably just a fire
    if source_type == "firms" and not flashpoint:
        score -= 10
        reasons.append("firms_no_flashpoint")

    score = max(0, min(100, score))
    return score, "|".join(reasons)


def score_to_priority(score: int) -> str:
    if score >= 70:
        return Priority.CRITICAL
    if score >= 45:
        return Priority.HIGH
    if score >= 25:
        return Priority.MEDIUM
    return Priority.LOW


# Trusted India defence/analysis sources — bypass relevance gate
INDIA_TRUSTED_SOURCES = [
    "pib", "livefist", "bharat shakti", "mp-idsa", "idsa", "carnegie india",
    "indian navy", "indian air force",
]

# Source → category mapping for India feeds
INDIA_SOURCE_CATEGORY = {
    "pib defence": "defence",
    "pib all": "official",
    "livefist defence": "defence",
    "bharat shakti": "defence",
    "mp-idsa": "analysis",
    "carnegie india": "analysis",
}

# India defence/geopolitical relevance keywords (for general news gate)
INDIA_RELEVANCE_KEYWORDS = [
    "india", "indian",
    "military", "defence", "defense", "army", "navy", "air force",
    "missile", "nuclear", "border", "lac", "china", "pakistan",
    "drdo", "isro", "brahmos", "tejas", "rafale", "submarine",
    "modi", "rajnath", "jaishankar", "diplomat", "bilateral",
    "terrorism", "militant", "ceasefire", "insurgent",
    "kashmir", "ladakh", "arunachal", "procurement", "weapons",
    "sanctions", "strategic", "indo-pacific", "quad",
]


def classify_event(event: dict) -> dict:
    """Classify an event: region, priority, flashpoint, source tier, dedup hash."""
    text = f"{event.get('title', '')} {event.get('summary', '')}".lower()
    source = event.get("source", "").lower()
    feed_region = event.get("region", "")
    feed_category = event.get("category", "")

    # Region: preserve feed-level tag if set, else classify from text
    if not feed_region:
        event["region"] = classify_region(text)

    # Flashpoint assignment
    event["flashpoint"] = classify_flashpoint(text, event.get("lat"), event.get("lon"))

    # Source tier (with fallback by source_type)
    source_type = event.get("source_type", "")
    event["source_tier"] = classify_source_tier(source, source_type)

    # Priority scoring (multi-factor, not just keywords)
    priority_score, priority_reason = compute_priority_score(text, event)
    event["priority"] = score_to_priority(priority_score)

    # Estimate Goldstein for events that don't have one (RSS, Telegram)
    if event.get("goldstein") is None:
        event["goldstein"] = estimate_goldstein(text)

    # Dedup hash
    event["dedup_hash"] = compute_dedup_hash(event.get("title", ""), event.get("source", ""))

    # India-specific: relevance gate + category
    if event["region"] == "india":
        # Source-based category (highest priority — known sources)
        matched_cat = INDIA_SOURCE_CATEGORY.get(source, "")
        if matched_cat:
            event["category"] = matched_cat
        elif feed_category:
            # Preserve feed-level category if set
            event["category"] = feed_category
        else:
            event["category"] = classify_india_category(text)

        # Relevance gate — even trusted Indian sources must mention India/Indian topics
        # (Bharat Shakti covering Iran ≠ India Command material)
        is_trusted = any(t in source for t in INDIA_TRUSTED_SOURCES)
        relevance_hits = sum(1 for kw in INDIA_RELEVANCE_KEYWORDS if _word_match(kw, text))
        if is_trusted:
            if relevance_hits < 1:
                event["region"] = ""
                event["category"] = ""
        else:
            if relevance_hits < 2:
                event["region"] = ""
                event["category"] = ""

    return event


def classify_region(text: str) -> str:
    """Classify region using whole-word matching."""
    scores = {}
    for region, keywords in REGION_KEYWORDS.items():
        score = sum(1 for kw in keywords if _word_match(kw, text))
        if score > 0:
            scores[region] = score

    if not scores:
        return ""
    return max(scores, key=scores.get)


def classify_flashpoint(text: str, lat: float | None, lon: float | None) -> str:
    for name, fp in FLASHPOINTS.items():
        if any(_word_match(kw, text) for kw in fp["keywords"]):
            return name

    if lat is not None and lon is not None:
        for name, fp in FLASHPOINTS.items():
            dist = haversine_km(lat, lon, fp["lat"], fp["lon"])
            if dist <= fp["radius_km"]:
                return name

    return ""


def classify_source_tier(source: str, source_type: str = "") -> str:
    for tier, patterns in SOURCE_TIERS.items():
        if any(p in source for p in patterns):
            return tier
    # Fallback: use source_type if no pattern matched
    fallback = SOURCE_TYPE_TIER_FALLBACK.get(source_type, "")
    if fallback:
        return fallback
    return SourceTier.UNKNOWN


def estimate_goldstein(text: str) -> float | None:
    """Estimate a Goldstein-like severity score for events that lack one (RSS, Telegram).
    Only returns a value when there are clear signals. Returns None for ambiguous text."""
    action_hits = sum(1 for kw in ACTION_KEYWORDS if _word_match(kw, text))
    escalation_hits = sum(1 for kw in ESCALATION_KEYWORDS if _word_match(kw, text))
    dampener_hits = sum(1 for kw in DAMPENER_KEYWORDS if _word_match(kw, text))

    if action_hits >= 3:
        return -9.0
    elif action_hits >= 2:
        return -7.0
    elif action_hits >= 1 and escalation_hits >= 1:
        return -6.0
    elif action_hits >= 1:
        return -4.0
    elif escalation_hits >= 2:
        return -5.0
    elif escalation_hits >= 1:
        return -3.0
    elif dampener_hits >= 3:
        return 1.5
    # No strong signals — don't assign a score
    return None


def _kw_match(keyword: str, text: str) -> bool:
    """Keyword match using word boundaries for all keywords."""
    return _word_match(keyword, text)


def classify_india_category(text: str) -> str:
    """Categorize India events — hybrid: short keywords use word boundary, long use substring."""
    procurement_kw = [
        "procurement", "contract", "tender", "acquisition", "defence order",
        "hal", "bhel", "bel", "drdo", "missile test", "rafale", "tejas", "arjun",
        "ins vikrant", "ins vikramaditya", "frigate", "corvette", "submarine",
        "fighter jet", "helicopter", "radar system", "s-400", "brahmos",
        "amca", "mmrca", "p-8i", "mig-29", "su-30", "c-130", "c-17",
        "shortlist", "clearance", "cleared", "clears", "induct",
        "commissioning", "delivered", "delivery", "fleet", "aircraft",
        "warship", "destroyer", "aircraft carrier", "stealth", "tanker",
        "mod clears", "ministry of defence", "dac", "defence acquisition",
        "make in india", "aatmanirbhar", "defence production",
        "arms deal", "weapons system", "defence deal",
    ]
    lac_kw = [
        "lac", "line of actual control", "pangong", "galwan",
        "doklam", "tawang", "arunachal", "ladakh", "aksai chin",
        "china border", "border standoff", "border tensions", "pla incursion",
        "india china border", "sino-indian", "eastern ladakh",
        "depsang", "hot springs", "gogra", "demchok",
        "border clash", "border face-off", "chinese troops",
        "itbp", "border roads", "bro",
    ]
    diplomacy_kw = [
        "jaishankar", "modi meets", "modi summit", "modi speaks", "bilateral",
        "diplomat", "diplomacy", "diplomatic",
        "foreign minister", "embassy", "high commission", "un general assembly",
        "g20", "quad", "brics", "sco summit", "foreign secretary",
        "external affairs", "foreign policy",
        "act east", "mea", "ministry of external affairs",
        "treaty", "accord", "alliance", "partnership",
        "state visit", "summit", "talks with", "dialogue",
        "indo-pacific", "multilateral", "nsa", "national security advisor",
        "speaks to", "phone call", "discussed",
    ]
    analysis_kw = [
        "orf online", "idsa", "carnegie india", "takshashila", "analysis",
        "commentary", "strategic assessment", "policy brief", "perspective",
        "opinion", "editorial", "lessons", "implications", "outlook",
        "what it means", "why india", "how india",
    ]
    space_kw = [
        "isro", "satellite launch", "pslv", "gslv", "chandrayaan",
        "gaganyaan", "aditya", "navic", "gsat", "insat",
        "sriharikota", "space command", "anti-satellite", "asat",
    ]
    nuclear_kw = [
        "barc", "nuclear submarine", "ins arihant", "ins arighat",
        "nuclear triad", "agni missile", "agni-v",
        "nuclear capable", "nuclear deterrent", "strategic forces command",
        "nuclear doctrine", "pokhran", "k-4 missile", "slbm", "atomic energy",
    ]

    if any(_kw_match(kw, text) for kw in lac_kw):
        return "lac"
    if any(_kw_match(kw, text) for kw in procurement_kw):
        return "procurement"
    if any(_kw_match(kw, text) for kw in diplomacy_kw):
        return "diplomacy"
    if any(_kw_match(kw, text) for kw in analysis_kw):
        return "analysis"
    if any(_kw_match(kw, text) for kw in space_kw):
        return "space"
    if any(_kw_match(kw, text) for kw in nuclear_kw):
        return "nuclear"
    return "defence"


def compute_dedup_hash(title: str, source: str) -> str:
    normalized = title.lower().strip()
    return hashlib.md5(f"{normalized}|{source}".encode()).hexdigest()[:16]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))
