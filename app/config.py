import os
import random
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "warroom.db"
FEEDS_PATH = DATA_DIR / "feeds.yml"
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ACLED (OAuth — uses your myACLED login credentials)
ACLED_EMAIL = os.getenv("ACLED_EMAIL", "")
ACLED_PASSWORD = os.getenv("ACLED_PASSWORD", "")

# NASA FIRMS
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")

# Proxy
HTTP_PROXY = os.getenv("HTTP_PROXY", "")
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")

# Alert thresholds
GOLDSTEIN_CRITICAL = float(os.getenv("GOLDSTEIN_CRITICAL", "-8"))
GOLDSTEIN_HIGH = float(os.getenv("GOLDSTEIN_HIGH", "-5"))
GOLDSTEIN_MEDIUM = float(os.getenv("GOLDSTEIN_MEDIUM", "-3"))

# Data retention
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))

# Source types that are map/spatial data only (not for text feed)
MAP_ONLY_SOURCE_TYPES = ("adsb", "firms", "usgs", "gdelt_geo")

# Anti-fingerprinting: User-Agent rotation pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/116.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
]


def get_random_ua() -> str:
    return random.choice(USER_AGENTS)


def get_jitter() -> float:
    """Random jitter ±30 seconds for poll intervals."""
    return random.uniform(-30, 30)


def get_httpx_kwargs() -> dict:
    """Common httpx client kwargs with proxy + UA rotation."""
    kwargs = {
        "headers": {"User-Agent": get_random_ua()},
        "timeout": 30.0,
        "follow_redirects": True,
    }
    if HTTPS_PROXY:
        kwargs["proxy"] = HTTPS_PROXY
    elif HTTP_PROXY:
        kwargs["proxy"] = HTTP_PROXY
    return kwargs


# Flashpoint definitions (lat, lon, radius_km)
FLASHPOINTS = {
    "Iran-Israel-US": {
        "lat": 32.0, "lon": 48.0, "radius_km": 2000,
        "keywords": [
            # Core actors
            "iran", "israel", "hezbollah", "houthi", "hamas",
            # Leaders / institutions
            "tehran", "idf", "irgc", "khamenei", "netanyahu", "nasrallah",
            "quds force", "centcom",
            # Locations
            "al-asad", "ain al-asad", "negev", "natanz", "dimona", "golan",
            "west bank", "rafah", "gaza", "beirut", "dahieh",
            "arak", "parchin", "isfahan", "bandar abbas",
            # Maritime / chokepoints
            "red sea", "hormuz", "strait of hormuz", "gulf of oman",
            "bab el-mandeb",
            # Weapons / systems
            "iron dome", "david's sling", "arrow missile",
            "shahed", "fateh",
        ],
    },
    "India-China LAC": {
        "lat": 33.5, "lon": 78.5, "radius_km": 800,
        "keywords": [
            "lac", "line of actual control", "pangong", "galwan",
            "doklam", "tawang", "arunachal", "ladakh", "aksai chin",
            "depsang", "hot springs", "gogra", "demchok", "chushul",
            "eastern ladakh", "itbp", "border roads",
            "china border", "sino-indian border",
        ],
    },
    "South China Sea": {
        "lat": 12.0, "lon": 114.0, "radius_km": 1500,
        "keywords": [
            "south china sea", "spratlys", "scarborough", "scarborough shoal",
            "second thomas", "second thomas shoal",
            "fiery cross", "mischief reef", "ccg", "philippine",
            "ayungin", "sierra madre", "whitsun reef", "paracel",
            "reed bank", "nine dash", "nine-dash line",
            "subi reef", "woody island",
            "philippine coast guard", "china coast guard", "sulu sea",
        ],
    },
    "Taiwan Strait": {
        "lat": 24.0, "lon": 120.0, "radius_km": 500,
        "keywords": [
            "taiwan", "taipei", "pla", "taiwan strait", "median line",
            "kinmen", "matsu", "lai ching-te", "william lai",
            "adiz", "taiwan adiz",
            "tsai ing-wen", "kaohsiung", "hualien",
            "eastern theater command",
        ],
    },
    "Russia-NATO": {
        "lat": 50.0, "lon": 35.0, "radius_km": 2000,
        "keywords": [
            "ukraine", "russia", "nato", "crimea", "donbas",
            "kherson", "zaporizhzhia", "kursk", "black sea fleet",
            "belgorod", "sumy", "kaliningrad", "bakhmut", "avdiivka",
            "pokrovsk", "tokmak",
            # Weapons / platforms
            "himars", "patriot", "leopard", "abrams", "challenger",
            "storm shadow", "scalp", "atacms", "gepard",
            "lancet", "iskander", "kinzhal",
            # Key figures / institutions
            "ramstein", "kyiv", "zelensky", "putin",
            "wagner", "akhmat",
        ],
    },
    "Korea": {
        "lat": 38.0, "lon": 127.0, "radius_km": 500,
        "keywords": [
            "north korea", "dprk", "pyongyang", "kim jong", "dmz",
            "icbm", "hwasong",
            "yongbyon", "punggye-ri", "kaesong", "panmunjom",
            "musudan", "unha",
            "usfk", "nll", "northern limit line",
        ],
    },
}

# Region classification (use specific phrases to avoid false positives)
REGION_KEYWORDS = {
    "india": [
        "indian navy", "indian air force", "indian army", "indian military",
        "new delhi", "modi", "rajnath", "jaishankar", "pib", "drdo", "isro",
        "tejas", "brahmos", "arjun", "rafale india", "ins vikrant",
        "arunachal", "ladakh", "kashmir", "lok sabha", "rajya sabha",
        "ministry of defence india", "indian ocean region",
        "ins arihant", "ins vikramaditya", "barc", "hal tejas",
    ],
    "middle_east": [
        "iran", "israel", "gaza", "hamas", "hezbollah", "houthi", "yemen", "syria",
        "iraq", "saudi", "uae", "lebanon", "idf", "irgc", "tehran", "netanyahu",
        "ayatollah", "khamenei",
        "red sea", "strait of hormuz", "gulf of oman", "aden",
        "suez", "sinai", "dimona", "rafah", "nasrallah",
        "west bank", "jenin", "nablus", "al-aqsa", "bab el-mandeb",
    ],
    "asia_pacific": [
        "china", "taiwan", "pla", "south china sea", "japan", "korea", "dprk",
        "asean", "philippines", "vietnam", "australia", "indo-pacific", "aukus",
        "beijing", "xi jinping", "pyongyang", "kim jong",
        "east china sea", "senkaku", "diaoyu", "sulu sea",
        "miyako strait", "first island chain",
    ],
    "europe": [
        "ukraine", "russia", "nato", "crimea", "baltic", "wagner",
        "putin", "zelensky", "scholz", "macron", "kyiv", "moscow",
        "donbas", "kherson", "zaporizhzhia", "kursk",
        "nordic", "article 5", "kaliningrad", "ramstein", "rutte",
    ],
    "africa": [
        "sudan", "khartoum", "rsf", "rapid support forces", "darfur",
        "ethiopia", "tigray", "amhara", "oromia", "addis ababa",
        "somalia", "al-shabaab", "mogadishu",
        "drc", "congo", "m23", "kivu",
        "sahel", "mali", "burkina faso", "niger",
        "african union", "ecowas",
        "boko haram", "lake chad",
    ],
}

# Country → region mapping (used by UCDP, ACLED, and other structured collectors)
COUNTRY_REGION_MAP = {
    # India (strict — only India itself goes to India Command)
    "India": "india",
    # South Asia neighbors (NOT India Command — visible in All feed)
    "Pakistan": "south_asia", "Nepal": "south_asia",
    "Sri Lanka": "south_asia", "Bangladesh": "south_asia", "Maldives": "south_asia",
    # Asia-Pacific
    "China": "asia_pacific", "Myanmar (Burma)": "asia_pacific", "Myanmar": "asia_pacific",
    "Philippines": "asia_pacific", "Japan": "asia_pacific",
    "South Korea": "asia_pacific", "Republic of Korea": "asia_pacific",
    "North Korea": "asia_pacific", "Korea, North": "asia_pacific",
    "Taiwan": "asia_pacific", "Vietnam": "asia_pacific",
    "Thailand": "asia_pacific", "Indonesia": "asia_pacific",
    "Malaysia": "asia_pacific", "Cambodia": "asia_pacific",
    "Laos": "asia_pacific", "Australia": "asia_pacific",
    # Middle East
    "Israel": "middle_east", "Iran": "middle_east", "Iraq": "middle_east",
    "Syria": "middle_east", "Yemen": "middle_east", "Lebanon": "middle_east",
    "Saudi Arabia": "middle_east", "Palestine": "middle_east",
    "Turkey": "middle_east", "Jordan": "middle_east",
    "United Arab Emirates": "middle_east", "Oman": "middle_east",
    "Qatar": "middle_east", "Bahrain": "middle_east", "Kuwait": "middle_east",
    "Egypt": "middle_east", "Libya": "middle_east",
    # Europe
    "Ukraine": "europe", "Russia": "europe", "Russia (Soviet Union)": "europe",
    "Belarus": "europe", "Poland": "europe", "Romania": "europe",
    "Moldova": "europe", "Georgia": "europe",
    "Armenia": "europe", "Azerbaijan": "europe",
    # Africa
    "Sudan": "africa", "South Sudan": "africa",
    "Ethiopia": "africa", "Somalia": "africa",
    "Democratic Republic of Congo": "africa", "DR Congo (Zaire)": "africa",
    "Mali": "africa", "Burkina Faso": "africa", "Niger": "africa",
    "Nigeria": "africa", "Chad": "africa",
    "Mozambique": "africa", "Central African Republic": "africa",
    "Cameroon": "africa",
}

# Region bounding boxes for map auto-zoom [[south, west], [north, east]]
REGION_BOUNDS = {
    "india": [[6, 68], [37, 98]],
    "middle_east": [[12, 25], [42, 65]],
    "asia_pacific": [[0, 95], [50, 150]],
    "europe": [[35, -10], [72, 60]],
    "africa": [[-35, -20], [38, 55]],
}

# Source reliability tiers
SOURCE_TIERS = {
    "WIRE": [
        "reuters", "associated press", "afp", "ap news",
        "al jazeera", "bbc", "ndtv", "times of israel", "middle east eye",
        "al-monitor", "scmp", "indian express", "the hindu",
        "military times", "usni news", "janes", "aninews", "ani news",
        "xinhua", "tass", "interfax", "yonhap",
    ],
    "GOV": [
        "pib", "mea", "mod.gov", "drdo", "state.gov", "defense.gov",
        "indiannavy", "iaf.nic", "fcdo", "ucdp",
    ],
    "OSINT": [
        "aurora intel", "osintdefender", "bno", "liveuamap",
        "intel slava", "war monitor", "conflict intelligence",
        "nexta", "the dead district", "flash news",
        "the war zone", "breaking defense", "defense one",
        "elint news", "middle east spectator", "me intel",
        "intel republic", "scs probing", "indo-pacific info",
        "africa intel", "sudan war map", "india defence news",
    ],
    "ANALYSIS": [
        "orf", "idsa", "csis", "rand", "carnegie", "war on the rocks",
        "iiss", "rusi", "brookings", "foreign affairs", "the diplomat",
        "foreign policy", "chatham house", "stimson", "hudson institute",
        "bharat shakti", "livefist", "jamestown",
    ],
}

# Fallback tier when source name doesn't match any pattern
SOURCE_TYPE_TIER_FALLBACK = {
    "telegram": "OSINT",
    "gdelt": "WIRE",
    "gdelt_geo": "WIRE",
    "ucdp": "GOV",
    "acled": "GOV",
    "rss": "UNKNOWN",
    "firms": "GOV",
    "usgs": "GOV",
    "adsb": "OSINT",
}
