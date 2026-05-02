import logging

logger = logging.getLogger("warroom.dedup")

# Common filler words to ignore during similarity comparison
_STOP_WORDS = frozenset({
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "are", "was", "were", "has", "have", "had", "been", "be",
    "it", "its", "this", "that", "with", "from", "by", "as", "not",
    "breaking", "update", "just", "now", "new", "says", "said",
    "report", "reports", "via", "per", "sources", "according",
})


def jaccard_similarity(text1: str, text2: str) -> float:
    """Jaccard similarity between two tokenized strings, with stop word removal."""
    tokens1 = set(text1.lower().split()) - _STOP_WORDS
    tokens2 = set(text2.lower().split()) - _STOP_WORDS
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


def is_duplicate(title: str, recent_titles: list[str], threshold: float = 0.55) -> bool:
    """Check if title is a near-duplicate of any recent title (cross-source dedup)."""
    for recent in recent_titles:
        sim = jaccard_similarity(title, recent)
        if sim >= threshold:
            logger.debug(f"Cross-source dedup: '{title[:60]}' ~ '{recent[:60]}' (sim={sim:.2f})")
            return True
    return False
