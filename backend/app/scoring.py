import re
from typing import Optional

STATUS_RANK = {"unsafe": 3, "caution": 2, "safe": 1, "unknown": 0}

# Bacteria results age out: full weight for a week (Sound Rivers samples
# weekly, DEQ weekly-to-biweekly in season), half weight for the second week,
# and after that the result is shown but no longer trusted to describe today.
BACTERIA_FULL_WEIGHT_DAYS = 7
BACTERIA_HALF_WEIGHT_DAYS = 14

_SAMPLE_STATUSES = {"unsafe", "caution", "safe"}
_SAMPLE_DESC = {
    "unsafe": "exceeds the swim standard",
    "caution": "elevated bacteria",
    "safe": "within the swim standard",
}

# Reports that count toward the verdict (the dashboard lists a longer window).
INCIDENT_SCORE_DAYS = 7
SPILL_SCORE_DAYS = 5
SPILL_CAUTION_GAL = 1_000

# How directly a site's water reflects River Bend's: its own shoreline first,
# then the rest of the Trent. Neuse sites are a different river -- shown on
# the dashboard, never allowed to drive the verdict.
_REACH_RANK = {"home": 0, "trent": 1}


def select_bacteria_reading(readings: list[dict]) -> Optional[dict]:
    """
    Pick the bacteria reading the verdict goes by. Freshness comes first:
    if anything was sampled in the last week, the score uses the most relevant
    reach that has a result that recent (River Bend's own shoreline over the
    rest of the Trent), and the worst result within it. Otherwise the same for
    the second week, newest first; past that, the newest result at all, which
    assess treats as too old to count. Neuse sites never qualify.

    Earlier versions ignored where a site was: a fixed source priority once let
    a month-old result override a 6-day-old one, and "worst of the freshest"
    let a fresh NW Creek sample -- on the Neuse, ~10 mi from River Bend --
    outrank Union Point at the mouth of the Trent.
    """
    eligible = [
        r for r in readings
        if r.get("status") in _SAMPLE_STATUSES and r.get("reach") in _REACH_RANK
    ]
    if not eligible:
        return None

    dated = [r for r in eligible if r.get("age_days") is not None]
    for max_age, pick_worst in ((BACTERIA_FULL_WEIGHT_DAYS, True), (BACTERIA_HALF_WEIGHT_DAYS, False)):
        window = [r for r in dated if r["age_days"] <= max_age]
        if not window:
            continue
        nearest = min(_REACH_RANK[r["reach"]] for r in window)
        reach = [r for r in window if _REACH_RANK[r["reach"]] == nearest]
        if pick_worst:
            return max(reach, key=lambda r: (STATUS_RANK[r["status"]], -r["age_days"]))
        return min(reach, key=lambda r: r["age_days"])

    if dated:
        return min(dated, key=lambda r: (r["age_days"], _REACH_RANK[r["reach"]]))
    return eligible[0]


# ── The verdict ──────────────────────────────────────────────────────────────
#
# No points. Every check produces a finding at one of four levels, and the
# worst finding sets the verdict:
#   avoid    stay out of the water
#   caution  swim with caution
#   note     worth knowing; the verdict doesn't change
#   clear    nothing found
# Findings come in two groups kept apart, so the headline says one thing:
# "water" (what's in the water) and "hazard" (weather and safety right now).
# The bacteria risk itself is the dashboard's headline number.
LEVEL_RANK = {"clear": 0, "note": 1, "caution": 2, "avoid": 3}
_VERDICT = {"clear": "good", "note": "good", "caution": "caution", "avoid": "avoid"}

# NWS alerts by what they mean for someone in the water (scale agreed Oct
# 2026): these warnings mean get out; any other relevant warning means
# caution; watches, advisories and statements are notes; alerts with nothing
# to do with swimming aren't counted at all.
_AVOID_ALERTS = {
    "Tornado Warning", "Severe Thunderstorm Warning", "Flash Flood Warning",
    "Hurricane Warning", "Tropical Storm Warning", "Storm Surge Warning",
    "Extreme Wind Warning", "Tsunami Warning", "Special Marine Warning",
}
_UNRELATED_ALERTS = re.compile(
    r"(?i)freeze|frost|fire|red flag|air quality|fog|winter|snow|ice|blizzard|cold|chill|dust|smoke|ashfall"
)


def _finding(key: str, group: str, label: str, level: str, reason: str) -> dict:
    return {"key": key, "group": group, "label": label, "level": level, "reason": reason}


def alert_level(event: str) -> Optional[str]:
    """What an NWS alert means for swimming; None when it doesn't bear on it."""
    if event in _AVOID_ALERTS:
        return "avoid"
    if _UNRELATED_ALERTS.search(event):
        return None
    if "Heat" in event:  # the water's the cool place to be; worth knowing, no more
        return "note"
    return "caution" if event.endswith("Warning") else "note"


def _sample_finding(reading: Optional[dict]) -> dict:
    label = "Latest bacteria sample"
    if reading is None:
        return _finding("sample", "water", label, "note", "No recent sample on the Trent — the prediction stands in")
    status, age, site = reading["status"], reading.get("age_days"), reading["site_name"].split(",")[0]
    desc = _SAMPLE_DESC[status]
    if age is None or age > BACTERIA_HALF_WEIGHT_DAYS:
        when = f"{age} days old" if age is not None else "undated"
        return _finding("sample", "water", label, "note",
                        f"{site}: {desc}, but {when} — too old to go by; the prediction stands in")
    fresh = age <= BACTERIA_FULL_WEIGHT_DAYS
    if status == "unsafe":
        level = "avoid" if fresh else "caution"
    elif status == "caution":
        level = "caution" if fresh else "note"
    else:
        level = "clear"
    suffix = "" if fresh or level == "clear" else " — over a week old, so it counts for less"
    return _finding("sample", "water", label, level, f"{site}: {desc}, sampled {age} days ago{suffix}")


def _risk_finding(risk: dict) -> dict:
    p, line = risk["probability"], risk["caution_probability"]
    chance = f"{p:.0%}" if p >= 0.01 else "<1%"
    notes = []
    if risk.get("rain_source") == "radar":
        notes.append("rain from radar — airport gauge unreliable")
    if risk["missing_inputs"]:
        notes.append(f"{', '.join(risk['missing_inputs'])} unavailable")
    extra = f" ({'; '.join(notes)})" if notes else ""
    label = "Predicted bacteria risk"
    if p >= line:
        return _finding("risk", "water", label, "caution",
                        f"{chance} chance of exceeding the swim standard — over the {line:.1%} Caution line{extra}")
    if risk["summer_storm"]:
        return _finding("risk", "water", label, "caution",
                        f"{risk['rain_72h_in']:.1f}\" of rain in 72h — big summer storms always mean caution "
                        f"({chance} modeled){extra}")
    return _finding("risk", "water", label, "clear",
                    f"{chance} chance of exceeding the swim standard — under the {line:.1%} Caution line{extra}")


def _spill_finding(spills: list[dict]) -> dict:
    label = "Sewage spills"
    recent = [s for s in spills if s["reached_water"] and (s["age_days"] <= SPILL_SCORE_DAYS or s["ongoing"])]
    if not recent:
        return _finding("spills", "water", label, "clear", f"None reaching the water nearby in {SPILL_SCORE_DAYS} days")

    def volume(s: dict) -> float:
        return s["volume_reached_water_gal"] or s["volume_gal"] or 0

    worst = max(recent, key=volume)
    gallons = volume(worst)
    amount = f"{gallons:,.0f} gal" if gallons else "Unknown volume"
    where = worst["waterbody"] or "surface water"
    when = "ongoing" if worst["ongoing"] else f"{worst['age_days']} days ago"
    dist = f", {worst['distance_mi']} mi away" if worst["distance_mi"] is not None else ""
    level = "caution" if gallons >= SPILL_CAUTION_GAL else "note"
    return _finding("spills", "water", label, level, f"{amount} reached {where} ({when}{dist})")


def _incident_finding(incidents: list[dict]) -> dict:
    label = "Fish kills & algal blooms"
    recent = [i for i in incidents if i["age_days"] <= INCIDENT_SCORE_DAYS]
    blooms = [i for i in recent if i["algal_bloom"]]
    kills = [i for i in recent if i["fish_kill"]]
    if blooms:
        b = blooms[0]
        return _finding("incidents", "water", label, "caution",
                        f"Algal bloom reported {b['date']} ({b['waterbody'] or 'nearby'}) — avoid discolored water or scum")
    if kills:
        nearest = min(kills, key=lambda k: k["distance_mi"] if k["distance_mi"] is not None else 99)
        dist = f", {nearest['distance_mi']} mi" if nearest["distance_mi"] is not None else ""
        return _finding("incidents", "water", label, "note",
                        f"{len(kills)} fish kill report{'s' if len(kills) != 1 else ''} in {INCIDENT_SCORE_DAYS} days "
                        f"(nearest: {nearest['waterbody'] or 'nearby'}{dist}) — usually low oxygen")
    return _finding("incidents", "water", label, "clear", f"None reported nearby in {INCIDENT_SCORE_DAYS} days")


def _alert_findings(alerts: Optional[list[dict]]) -> list[dict]:
    if alerts is None:
        return [_finding("alerts", "hazard", "NWS alerts", "note", "Couldn't reach the National Weather Service")]
    found = []
    for a in alerts:
        level = alert_level(a["event"])
        if level is not None:
            until = f" until {a['ends'][:16].replace('T', ' ')}" if a.get("ends") else ""
            found.append(_finding(f"alert:{a['event']}", "hazard", a["event"], level,
                                  a.get("headline") or f"In effect{until}"))
    return found or [_finding("alerts", "hazard", "NWS alerts", "clear", "No alerts that bear on swimming")]


def _thunder_finding(pct: int) -> dict:
    label = "Lightning, next 6 hours"
    if pct >= 55:
        return _finding("thunder", "hazard", label, "caution", f"{pct}% chance of thunder — get out at the first rumble")
    if pct >= 25:
        return _finding("thunder", "hazard", label, "note", f"{pct}% chance of thunder — storms possible")
    return _finding("thunder", "hazard", label, "clear", f"{pct}% chance of thunder")


def assess(
    bacteria: Optional[dict],
    bacteria_risk: Optional[dict],
    nws_alerts: Optional[list[dict]] = None,
    thunder_pct_6h: Optional[int] = None,
    incidents: Optional[list[dict]] = None,
    sewer_spills: Optional[list[dict]] = None,
) -> dict:
    """Today's verdict (good / caution / avoid) and every finding behind it, worst first within each group."""
    findings = [_sample_finding(bacteria)]
    if bacteria_risk is not None:
        findings.append(_risk_finding(bacteria_risk))
    if sewer_spills is not None:
        findings.append(_spill_finding(sewer_spills))
    if incidents is not None:
        findings.append(_incident_finding(incidents))
    findings += _alert_findings(nws_alerts)
    if thunder_pct_6h is not None:
        findings.append(_thunder_finding(thunder_pct_6h))

    worst = max((f["level"] for f in findings), key=LEVEL_RANK.__getitem__, default="clear")
    verdict = _VERDICT[worst]
    findings.sort(key=lambda f: (f["group"] != "water", -LEVEL_RANK[f["level"]]))
    return {"verdict": verdict, "findings": findings}


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
