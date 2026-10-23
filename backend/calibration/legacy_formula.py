"""
The dashboard's rain and flow rules as they stood before the bacteria-risk
model replaced them (retired 2026-10-07), frozen here so the baseline and
every future model keep being graded against the same yardstick.
"""
NO_BACTERIA_DATA_IMPACT = -5


def rating_for(score: int) -> tuple[str, str]:
    """The retired 0-100 score's rating bands."""
    if score >= 85:
        return "Excellent", "green"
    if score >= 70:
        return "Good", "blue"
    if score >= 50:
        return "Caution", "yellow"
    return "Avoid Swimming", "red"


def legacy_penalty(rain_24h, rain_72h, flow_cfs, flow_p80) -> int:
    penalty = 0
    if rain_24h is not None:
        if rain_24h > 1.0:
            penalty -= 20
        elif rain_24h > 0.5:
            penalty -= 10
    if rain_72h is not None:
        if rain_72h > 2.0:
            penalty -= 15
        elif rain_72h > 1.0:
            penalty -= 8
    if flow_cfs is not None and flow_p80 is not None and flow_cfs > flow_p80:
        penalty -= 10
    return penalty


def legacy_score(rain_24h, rain_72h, flow_cfs, flow_p80) -> tuple[int, str, int]:
    """Score, rating and rain/flow penalty the old dashboard showed with no fresh bacteria result."""
    penalty = legacy_penalty(rain_24h, rain_72h, flow_cfs, flow_p80)
    score = max(0, min(100, 100 + NO_BACTERIA_DATA_IMPACT + penalty))
    rating, _ = rating_for(score)
    return score, rating, penalty
