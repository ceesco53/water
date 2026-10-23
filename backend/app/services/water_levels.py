import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..geo import miles_from_home

logger = logging.getLogger(__name__)

# NOAA's National Water Prediction Service: official river gauges, with the
# NWS flood categories for each. It republishes the operators' readings --
# NC Dept of Public Safety's FIMAN network and USGS.
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges"

# The three Trent River gauges nearest River Bend. Jack Smith Creek at New
# Bern (JSMN7, ~6 mi) is closer than New Bern but is a small tributary creek
# with no flood stages, so it's left out.
GAUGES = [
    {"lid": "RBDN7", "short": "River Bend", "position": "your stretch"},
    {"lid": "PLLN7", "short": "Pollocksville", "position": "upstream"},
    {"lid": "BERN7", "short": "New Bern", "position": "downstream"},
]

DAYS = 7
_CATEGORIES = ("action", "minor", "moderate", "major")


def _category(stage: float, stages: dict[str, float | None]) -> str:
    """NWS flood category for a stage: normal, action, or minor/moderate/major flooding."""
    current = "normal"
    for name in _CATEGORIES:
        threshold = stages.get(name)
        if threshold is not None and stage >= threshold:
            current = name
    return current


def _operator(attribution: str) -> str | None:
    if "USGS" in attribution or "Geological" in attribution:
        return "USGS"
    if "Public Safety" in attribution:
        return "NC Public Safety (FIMAN)"
    return attribution.strip() or None


def _hourly(points: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Average 5-15 minute readings into hourly means -- plenty for a 7-day chart."""
    buckets: dict[datetime, list[float]] = {}
    for t, v in points:
        buckets.setdefault(t.replace(minute=0, second=0, microsecond=0), []).append(v)
    return [(t, sum(vs) / len(vs)) for t, vs in sorted(buckets.items())]


async def _fetch_gauge(client: httpx.AsyncClient, gauge: dict) -> dict | None:
    lid = gauge["lid"]
    meta_resp, obs_resp = await asyncio.gather(
        client.get(f"{NWPS}/{lid}"),
        client.get(f"{NWPS}/{lid}/stageflow/observed"),
    )
    meta_resp.raise_for_status()
    obs_resp.raise_for_status()
    meta, obs = meta_resp.json(), obs_resp.json()

    since = datetime.now(timezone.utc) - timedelta(days=DAYS)
    raw = []
    for p in obs.get("data", []):
        try:
            t = datetime.fromisoformat(p["validTime"].replace("Z", "+00:00"))
            v = float(p["primary"])
        except (KeyError, TypeError, ValueError):
            continue
        if t >= since and v > -900:  # NWPS marks missing values as -999
            raw.append((t, v))
    if not raw:
        return None

    stages = {
        name: (stage if stage is not None and stage > -900 else None)
        for name in _CATEGORIES
        for stage in [((meta.get("flood") or {}).get("categories") or {}).get(name, {}).get("stage")]
    }
    latest_t, latest_v = max(raw)
    day_ago = latest_t - timedelta(hours=24)
    earlier = [v for t, v in raw if t <= day_ago]
    name = meta.get("name") or gauge["short"]
    attribution = " ".join(
        f"{a.get('abbrev', '')} {a.get('title', '')}" for a in meta.get("dataAttribution") or []
    )

    return {
        "id": lid,
        "name": name.replace("(in MLLW)", "").strip(),
        "short": gauge["short"],
        "position": gauge["position"],
        "distance_mi": round(miles_from_home(meta["latitude"], meta["longitude"]), 1),
        # FIMAN gauges report feet above mean lower low water; USGS ones, gage
        # height above the station's own datum. Neither compares across gauges.
        "datum": "MLLW" if "MLLW" in name else "gage datum",
        "operator": _operator(attribution),
        "latest_ft": round(latest_v, 2),
        "latest_time": latest_t.isoformat(),
        "change_24h_ft": round(latest_v - earlier[-1], 2) if earlier else None,
        "category": _category(latest_v, stages),
        "flood_stages": stages,
        "series": [[t.isoformat(), round(v, 2)] for t, v in _hourly(raw)],
        "url": f"https://water.noaa.gov/gauges/{lid.lower()}",
    }


async def fetch_water_levels() -> list[dict]:
    """Last DAYS of water level at each gauge, nearest first; gauges that fail are skipped."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        results = await asyncio.gather(*(_fetch_gauge(client, g) for g in GAUGES), return_exceptions=True)
    levels = []
    for gauge, result in zip(GAUGES, results):
        if isinstance(result, Exception):
            logger.warning("NWPS water level fetch failed for %s: %s", gauge["lid"], result)
        elif result is not None:
            levels.append(result)
    return sorted(levels, key=lambda g: g["distance_mi"])


# A gauge counts as "up" when it's at action stage or higher, or has risen
# this much in 24 hours.
RISE_FT = 0.25
# NWS alerts that speak to water levels, in their own words
_WATER_ALERT = re.compile(r"(?i)flood|surge|tropical|hurricane|hydrologic|tsunami")


def level_context(levels: list[dict], alerts: list[dict] | None, discussion: dict | None) -> dict:
    """
    Official explanations for high or rising water: water-related NWS alerts
    covering HOME, and the water passages of the latest NWS forecast
    discussion -- quoted, never paraphrased. `elevated` says whether any gauge
    is up enough to show them.
    """
    return {
        "elevated": any(
            g["category"] != "normal" or (g.get("change_24h_ft") or 0) >= RISE_FT for g in levels
        ),
        "alerts": [a for a in alerts or [] if _WATER_ALERT.search(a.get("event") or "")],
        "discussion": discussion,
    }


# Hours of overlap needed to measure a station's offset from its gauge
_MIN_OVERLAP_HOURS = 6
_TROPICAL = re.compile(r"(?i)tropical|hurricane")


def attach_guidance(levels: list[dict], guidance: dict[str, dict], alerts: list[dict] | None) -> bool:
    """
    Add P-ETSS guidance to each gauge it covers, as `guidance`. Returns False
    -- attaching nothing -- while a tropical storm or hurricane alert is
    active, since NWS says the guidance doesn't apply then.

    P-ETSS's stations don't always share the gauge's datum (New Bern's runs
    ~0.28 ft below FIMAN's MLLW), so each forecast is shifted by the median
    gap between P-ETSS's own observed values and the gauge's readings over
    the hours they overlap. Without enough overlap to measure that gap, the
    gauge gets no guidance rather than a possibly misaligned one.
    """
    if any(_TROPICAL.search(a.get("event") or "") for a in alerts or []):
        for g in levels:
            g["guidance"] = None
        return False

    for g in levels:
        g["guidance"] = None
        gd = guidance.get(g["id"])
        if not gd:
            continue
        gauge_hourly = {datetime.fromisoformat(t): v for t, v in g["series"]}
        model_hourly = dict(_hourly(gd["obs"]))
        gaps = sorted(gauge_hourly[t] - v for t, v in model_hourly.items() if t in gauge_hourly)
        if len(gaps) < _MIN_OVERLAP_HOURS:
            continue
        offset = gaps[len(gaps) // 2]
        # From the start of the model run, not from now: where the guidance
        # overlaps the gauge's own readings, it shows how well it's tracking.
        points = [
            [t.isoformat(), round(v + offset, 2), round(lo + offset, 2), round(hi + offset, 2)]
            for t, v, lo, hi in gd["forecast"]
        ]
        latest = datetime.fromisoformat(g["latest_time"])
        ahead = [p for p in points if datetime.fromisoformat(p[0]) > latest]
        if not ahead:
            continue
        peak = max(ahead, key=lambda p: p[1])
        g["guidance"] = {
            "source": "NWS P-ETSS storm-surge model guidance",
            "run": gd["run"],
            "points": points,  # [iso time, ft, 80%-range low, 80%-range high]
            "peak": {"time": peak[0], "ft": peak[1]},
            "offset_ft": round(offset, 2),
            "url": gd["url"],
        }
    return True
