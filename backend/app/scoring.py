from typing import Optional


def compute_score(
    swimguide_status: str,
    rain_24h_in: Optional[float],
    rain_72h_in: Optional[float],
    upstream_discharge_cfs: Optional[float],
    upstream_discharge_p80: Optional[float],
) -> tuple[int, str, str, list[dict]]:
    score = 100
    factors: list[dict] = []

    # Bacteria — highest weight, primary safety signal
    # api_unavailable = partner key required (not a water quality issue — no penalty)
    if swimguide_status == "unsafe":
        score -= 60
        factors.append({"label": "Bacteria (Swim Guide)", "impact": -60,
                         "reason": "Active unsafe advisory — do not swim"})
    elif swimguide_status == "caution":
        score -= 30
        factors.append({"label": "Bacteria (Swim Guide)", "impact": -30,
                         "reason": "Caution advisory in effect"})
    elif swimguide_status == "api_unavailable":
        factors.append({"label": "Bacteria (Swim Guide)", "impact": 0,
                         "reason": "API requires partner key — check Sound Rivers directly"})
    elif swimguide_status == "unknown":
        score -= 5
        factors.append({"label": "Bacteria (Swim Guide)", "impact": -5,
                         "reason": "No recent sampling data available"})
    else:
        factors.append({"label": "Bacteria (Swim Guide)", "impact": 0,
                         "reason": "Safe — bacteria levels acceptable"})

    # Rainfall 24h — runoff contamination risk
    if rain_24h_in is not None:
        if rain_24h_in > 1.0:
            score -= 20
            factors.append({"label": "Rainfall (24h)", "impact": -20,
                             "reason": f"{rain_24h_in:.2f}\" — heavy runoff risk"})
        elif rain_24h_in > 0.5:
            score -= 10
            factors.append({"label": "Rainfall (24h)", "impact": -10,
                             "reason": f"{rain_24h_in:.2f}\" — moderate runoff risk"})
        else:
            factors.append({"label": "Rainfall (24h)", "impact": 0,
                             "reason": f"{rain_24h_in:.2f}\" — minimal rainfall"})

    # Rainfall 72h — contamination window (48–72h is peak risk in eastern NC)
    if rain_72h_in is not None:
        if rain_72h_in > 2.0:
            score -= 15
            factors.append({"label": "Rainfall (72h)", "impact": -15,
                             "reason": f"{rain_72h_in:.2f}\" — within peak contamination window"})
        elif rain_72h_in > 1.0:
            score -= 8
            factors.append({"label": "Rainfall (72h)", "impact": -8,
                             "reason": f"{rain_72h_in:.2f}\" — elevated 72h accumulation"})
        else:
            factors.append({"label": "Rainfall (72h)", "impact": 0,
                             "reason": f"{rain_72h_in:.2f}\" — dry period, low risk"})

    # Upstream discharge — flushing / runoff indicator
    if upstream_discharge_cfs is not None and upstream_discharge_p80 is not None:
        if upstream_discharge_cfs > upstream_discharge_p80:
            score -= 10
            factors.append({"label": "Upstream Flow", "impact": -10,
                             "reason": (f"{upstream_discharge_cfs:.0f} ft³/s — above 7-day "
                                        f"80th pct ({upstream_discharge_p80:.0f}), elevated flushing")})
        else:
            factors.append({"label": "Upstream Flow", "impact": 0,
                             "reason": f"{upstream_discharge_cfs:.0f} ft³/s — normal range"})

    score = max(0, min(100, score))

    if score >= 85:
        rating, color = "Excellent", "green"
    elif score >= 70:
        rating, color = "Good", "blue"
    elif score >= 50:
        rating, color = "Caution", "yellow"
    else:
        rating, color = "Avoid Swimming", "red"

    return score, rating, color, factors
