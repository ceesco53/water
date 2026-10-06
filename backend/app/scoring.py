from typing import Optional

STATUS_RANK = {"unsafe": 3, "caution": 2, "safe": 1, "unknown": 0}

# Bacteria results age out: full weight for a week (Sound Rivers samples
# weekly, DEQ weekly-to-biweekly in season), half weight for the second week,
# and after that the result is shown but no longer trusted to describe today.
BACTERIA_FULL_WEIGHT_DAYS = 7
BACTERIA_HALF_WEIGHT_DAYS = 14

_BACTERIA_IMPACT = {"unsafe": -60, "caution": -30, "safe": 0}
_BACTERIA_DESC = {
    "unsafe": "exceeds swimming standard",
    "caution": "elevated bacteria",
    "safe": "within swimming standard",
}

# Reports that count toward the score (the dashboard lists a longer window).
INCIDENT_SCORE_DAYS = 7
SPILL_SCORE_DAYS = 5

_ALERT_IMPACT = {"Extreme": -50, "Severe": -30, "Moderate": -10}


def select_bacteria_reading(readings: list[dict]) -> Optional[dict]:
    """
    Pick the bacteria reading that drives the score. Every reading sampled
    within the last week counts as current, and the worst of those wins — a
    fresh fail at River Bend shouldn't be outvoted by a fresh pass six miles
    away. With nothing that recent, the newest reading wins regardless of
    source, and compute_score discounts it by age. (Previously a fixed source
    priority let a month-old Sound Rivers result override a 6-day-old DEQ one.)
    """
    known = [r for r in readings if r.get("status") in _BACTERIA_IMPACT]
    if not known:
        return None
    dated = [r for r in known if r.get("age_days") is not None]
    current = [r for r in dated if r["age_days"] <= BACTERIA_FULL_WEIGHT_DAYS]
    if current:
        return max(current, key=lambda r: (STATUS_RANK[r["status"]], -r["age_days"]))
    if dated:
        return min(dated, key=lambda r: r["age_days"])
    return known[0]


def _bacteria_factor(reading: Optional[dict]) -> dict:
    if reading is None:
        return {"label": "Bacteria", "impact": -5,
                "reason": "No sampling data available — rain and flow stand in"}

    label = f"Bacteria ({reading['source']})"
    status = reading["status"]
    age = reading.get("age_days")
    site = reading["site_name"]
    desc = _BACTERIA_DESC[status]
    base = _BACTERIA_IMPACT[status]

    if age is not None and age > BACTERIA_HALF_WEIGHT_DAYS:
        return {"label": label, "impact": -5,
                "reason": (f"Newest sample is {age}d old ({site}: {desc}) — "
                           "too old to count; rain and flow stand in")}
    if age is not None and age <= BACTERIA_FULL_WEIGHT_DAYS:
        suffix = " — do not swim" if status == "unsafe" else ""
        return {"label": label, "impact": base,
                "reason": f"{site}: {desc}, sampled {age}d ago{suffix}"}

    when = f"sampled {age}d ago" if age is not None else "sample date unknown"
    return {"label": label, "impact": round(base / 2),
            "reason": f"{site}: {desc}, {when} — counts half"}


def _incident_factor(incidents: list[dict]) -> dict:
    recent = [i for i in incidents if i["age_days"] <= INCIDENT_SCORE_DAYS]
    blooms = [i for i in recent if i["algal_bloom"]]
    kills = [i for i in recent if i["fish_kill"]]

    impact = 0
    reasons = []
    if blooms:
        impact -= 15
        b = blooms[0]
        reasons.append(f"algal bloom reported {b['date']} ({b['waterbody'] or 'nearby'}) — avoid discolored water or scum")
    if kills:
        impact -= 10
        nearest = min(kills, key=lambda k: k["distance_mi"] if k["distance_mi"] is not None else 99)
        where = nearest["waterbody"] or "nearby"
        dist = f", {nearest['distance_mi']} mi" if nearest["distance_mi"] is not None else ""
        reasons.append(f"{len(kills)} fish kill report{'s' if len(kills) != 1 else ''} in {INCIDENT_SCORE_DAYS}d "
                       f"(nearest: {where}{dist}) — likely low oxygen")
    if not reasons:
        reasons.append(f"None reported nearby in {INCIDENT_SCORE_DAYS}d")

    return {"label": "Fish Kills & Algal Blooms", "impact": impact, "reason": "; ".join(reasons)}


def _spill_factor(spills: list[dict]) -> dict:
    recent = [
        s for s in spills
        if s["reached_water"] and (s["age_days"] <= SPILL_SCORE_DAYS or s["ongoing"])
    ]
    if not recent:
        return {"label": "Sewage Spills", "impact": 0,
                "reason": f"None reaching water nearby in {SPILL_SCORE_DAYS}d"}

    def volume(s: dict) -> float:
        return s["volume_reached_water_gal"] or s["volume_gal"] or 0

    worst = max(recent, key=volume)
    gallons = volume(worst)
    if gallons >= 10_000:
        impact = -30
    elif gallons >= 1_000:
        impact = -15
    else:
        impact = -5

    amount = f"{gallons:,.0f} gal" if gallons else "Unknown volume"
    where = worst["waterbody"] or "surface water"
    when = "ongoing" if worst["ongoing"] else f"{worst['age_days']}d ago"
    dist = f", {worst['distance_mi']} mi away" if worst["distance_mi"] is not None else ""
    return {"label": "Sewage Spills", "impact": impact,
            "reason": f"{amount} reached {where} ({when}{dist})"}


def compute_score(
    bacteria: Optional[dict],
    rain_24h_in: Optional[float],
    rain_72h_in: Optional[float],
    upstream_discharge_cfs: Optional[float],
    upstream_discharge_p80: Optional[float],
    nws_alerts: Optional[list[dict]] = None,
    thunder_pct_6h: Optional[int] = None,
    incidents: Optional[list[dict]] = None,
    sewer_spills: Optional[list[dict]] = None,
) -> tuple[int, str, str, list[dict]]:
    score = 100
    factors: list[dict] = []

    def add(factor: dict) -> None:
        nonlocal score
        score += factor["impact"]
        factors.append(factor)

    # Bacteria — highest weight, primary safety signal
    add(_bacteria_factor(bacteria))

    # Rainfall 24h — runoff contamination risk
    if rain_24h_in is not None:
        if rain_24h_in > 1.0:
            add({"label": "Rainfall (24h)", "impact": -20,
                 "reason": f"{rain_24h_in:.2f}\" — heavy runoff risk"})
        elif rain_24h_in > 0.5:
            add({"label": "Rainfall (24h)", "impact": -10,
                 "reason": f"{rain_24h_in:.2f}\" — moderate runoff risk"})
        else:
            add({"label": "Rainfall (24h)", "impact": 0,
                 "reason": f"{rain_24h_in:.2f}\" — minimal rainfall"})

    # Rainfall 72h — contamination window (48–72h is peak risk in eastern NC)
    if rain_72h_in is not None:
        if rain_72h_in > 2.0:
            add({"label": "Rainfall (72h)", "impact": -15,
                 "reason": f"{rain_72h_in:.2f}\" — within peak contamination window"})
        elif rain_72h_in > 1.0:
            add({"label": "Rainfall (72h)", "impact": -8,
                 "reason": f"{rain_72h_in:.2f}\" — elevated 72h accumulation"})
        else:
            add({"label": "Rainfall (72h)", "impact": 0,
                 "reason": f"{rain_72h_in:.2f}\" — dry period, low risk"})

    # Upstream discharge — flushing / runoff indicator
    if upstream_discharge_cfs is not None and upstream_discharge_p80 is not None:
        if upstream_discharge_cfs > upstream_discharge_p80:
            add({"label": "Upstream Flow", "impact": -10,
                 "reason": (f"{upstream_discharge_cfs:.0f} ft³/s — above the historical "
                            f"80th pct for today ({upstream_discharge_p80:.0f}), elevated runoff")})
        else:
            add({"label": "Upstream Flow", "impact": 0,
                 "reason": f"{upstream_discharge_cfs:.0f} ft³/s — normal range"})

    # Sewage reaching the water — direct bacteria source
    if sewer_spills is not None:
        add(_spill_factor(sewer_spills))

    # Fish kills / algal blooms — low oxygen, possible toxins
    if incidents is not None:
        add(_incident_factor(incidents))

    # NWS alerts — storms, floods, heat; only the most severe counts
    if nws_alerts is not None:
        if nws_alerts:
            worst = max(nws_alerts, key=lambda a: -_ALERT_IMPACT.get(a.get("severity"), 0))
            more = f" (+{len(nws_alerts) - 1} more)" if len(nws_alerts) > 1 else ""
            add({"label": "NWS Alerts", "impact": _ALERT_IMPACT.get(worst.get("severity"), 0),
                 "reason": f"{worst['event']} in effect{more}"})
        else:
            add({"label": "NWS Alerts", "impact": 0, "reason": "No active alerts"})

    # Lightning — the most immediate swim hazard
    if thunder_pct_6h is not None:
        if thunder_pct_6h >= 55:
            add({"label": "Thunder (6h)", "impact": -20,
                 "reason": f"{thunder_pct_6h}% — storms likely; get out at the first rumble"})
        elif thunder_pct_6h >= 25:
            add({"label": "Thunder (6h)", "impact": -10,
                 "reason": f"{thunder_pct_6h}% — storms possible"})
        else:
            add({"label": "Thunder (6h)", "impact": 0,
                 "reason": f"{thunder_pct_6h}% — low lightning risk"})

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


# Vibrio vulnificus multiplies in warm, brackish water: growth is suppressed
# below ~68°F (20°C), and it favors roughly 5–25 ppt salinity. The Trent at
# River Bend sits in that salinity band most summers. This is shown as its own
# advisory rather than scored: the risk is serious but concentrated in people
# with open wounds, liver disease, or weakened immunity.
_VIBRIO_MIN_TEMP_F = 68
_VIBRIO_HIGH_TEMP_F = 80
_VIBRIO_SALINITY_PPT = (5, 25)


def vibrio_risk(water_temp_f: Optional[float], salinity_ppt: Optional[float]) -> dict:
    if water_temp_f is None:
        return {"level": "unknown", "reason": "No water temperature available"}
    if water_temp_f < _VIBRIO_MIN_TEMP_F:
        return {"level": "low", "reason": f"Water {water_temp_f:.0f}°F — too cool for Vibrio growth"}

    lo, hi = _VIBRIO_SALINITY_PPT
    if salinity_ppt is not None and not (lo <= salinity_ppt <= hi):
        return {"level": "low",
                "reason": f"Salinity {salinity_ppt:g} ppt — outside the {lo}–{hi} ppt range Vibrio favors"}

    salinity_note = (f"{salinity_ppt:g} ppt salinity" if salinity_ppt is not None
                     else "salinity unknown (usually brackish here)")
    if water_temp_f >= _VIBRIO_HIGH_TEMP_F and salinity_ppt is not None:
        return {"level": "high", "reason": f"{water_temp_f:.0f}°F, {salinity_note} — peak Vibrio conditions"}
    return {"level": "elevated", "reason": f"{water_temp_f:.0f}°F, {salinity_note} — Vibrio can grow"}
