from pydantic import BaseModel
from typing import Optional
from enum import Enum


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceTier(str, Enum):
    WIRE = "WIRE"
    GOV = "GOV"
    OSINT = "OSINT"
    ANALYSIS = "ANALYSIS"
    UNKNOWN = "UNKNOWN"


class EventSource(str, Enum):
    RSS = "rss"
    GDELT = "gdelt"
    ACLED = "acled"
    FIRMS = "firms"
    USGS = "usgs"
    ADSB = "adsb"
    TELEGRAM = "telegram"
    GPSJAM = "gpsjam"
    TRAVEL_ADVISORY = "travel_advisory"


class FlashpointStatus(str, Enum):
    BASELINE = "baseline"
    STABLE = "stable"
    ELEVATED = "elevated"
    ESCALATING = "escalating"
    CRITICAL = "critical"


class Event(BaseModel):
    id: Optional[int] = None
    title: str
    summary: str = ""
    url: str = ""
    source: str = ""
    source_type: EventSource = EventSource.RSS
    source_tier: SourceTier = SourceTier.UNKNOWN
    region: str = ""
    category: str = ""
    priority: Priority = Priority.LOW
    goldstein: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    image_url: str = ""
    fatalities: int = 0
    flashpoint: str = ""
    is_read: bool = False
    is_pinned: bool = False
    created_at: Optional[str] = None


class Flashpoint(BaseModel):
    name: str
    status: FlashpointStatus = FlashpointStatus.BASELINE
    score: float = 0.0
    last_event_time: Optional[str] = None
    event_count_24h: int = 0
    event_count_7d: list[int] = []  # 7 daily counts for sparkline
