from app.config import FLASHPOINTS
from app.database import get_flashpoint_stats
from app.models import Flashpoint, FlashpointStatus


def score_to_status(score: float) -> FlashpointStatus:
    if score >= 81:
        return FlashpointStatus.CRITICAL
    if score >= 61:
        return FlashpointStatus.ESCALATING
    if score >= 41:
        return FlashpointStatus.ELEVATED
    if score >= 21:
        return FlashpointStatus.STABLE
    return FlashpointStatus.BASELINE


def compute_escalation_score(stats: dict) -> float:
    """
    Compute 0-100 escalation score for a flashpoint.

    Formula:
      event_frequency * 0.35
    + goldstein_severity * 0.25
    + firms_thermal * 0.20
    + source_diversity * 0.10
    + fatalities * 0.10
    """
    # Event frequency: normalize against a baseline of ~10 events/day
    freq_score = min(100, (stats["count_24h"] / 10) * 100) * 0.35

    # Goldstein severity: -10 = 100, 0 = 0 (invert and normalize)
    avg_g = stats.get("avg_goldstein", 0) or 0
    goldstein_score = min(100, max(0, (-avg_g / 10) * 100)) * 0.25

    # FIRMS thermal: any hits in a conflict zone are significant
    firms_score = min(100, stats["firms_count"] * 25) * 0.20

    # Source diversity: more sources = more significant
    diversity_score = min(100, stats["source_diversity"] * 15) * 0.10

    # Fatalities: normalize against ~50
    fatality_score = min(100, (stats["fatalities"] / 50) * 100) * 0.10

    total = freq_score + goldstein_score + firms_score + diversity_score + fatality_score
    return min(100, max(0, total))


async def compute_all_flashpoints() -> list[dict]:
    """Compute status for all defined flashpoints."""
    results = []
    for name in FLASHPOINTS:
        try:
            stats = await get_flashpoint_stats(name)
            score = compute_escalation_score(stats)
            status = score_to_status(score)

            results.append({
                "name": name,
                "status": status.value,
                "score": round(score, 1),
                "last_event_time": stats["last_event"],
                "event_count_24h": stats["count_24h"],
                "event_count_7d": stats["daily_counts"],
            })
        except Exception:
            results.append({
                "name": name,
                "status": FlashpointStatus.BASELINE.value,
                "score": 0,
                "last_event_time": None,
                "event_count_24h": 0,
                "event_count_7d": [0] * 7,
            })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results
