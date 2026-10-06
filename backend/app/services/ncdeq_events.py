import logging
from datetime import timedelta

import httpx

from ..geo import miles_from_river_bend
from .arcgis import epoch_ms_to_date, query_layer, since, utc_today, within_miles_of_river_bend

logger = logging.getLogger(__name__)

FISH_KILL_SERVICE = "North_Carolina_Fish_Kills_and_Algal_Blooms_Public_Reports"

# DEQ publishes sewer overflows in date-ranged services (the previous one ran
# Sept 2022 – Dec 2025). If this one stops resolving — say, superseded by a
# "since Jan 2027" service — the fetch logs a warning and the dashboard shows
# the feed as unavailable rather than claiming there were no spills.
SSO_SERVICE = "Sanitary_Sewer_Overflows_since_Jan_2026"

# Pollocksville (~6 mi up the Trent) through Union Point (~6.7 mi down).
RADIUS_MI = 8
LOOKBACK_DAYS = 14


def _text(value) -> str | None:
    s = (value or "").strip() if isinstance(value, str) else None
    return s or None


def _yes(value) -> bool:
    # Coded "Yes"/"No" values arrive space-padded ("No      ")
    return isinstance(value, str) and value.strip().lower() == "yes"


def _distance(row: dict, lat_key: str = "lat", lon_key: str = "lon") -> float | None:
    lat, lon = row.get(lat_key), row.get(lon_key)
    if lat is None or lon is None:
        return None
    return round(miles_from_river_bend(lat, lon), 1)


async def fetch_water_incidents() -> list[dict] | None:
    """
    Fish kills and algal blooms reported to NC DEQ near River Bend in the
    last LOOKBACK_DAYS, newest first. Fish kills in the lower Neuse/Trent are
    usually low-oxygen events, which tend to travel with algal blooms — and
    some blooms (cyanobacteria) produce toxins. Returns None if the feed is
    unreachable, so "no reports" and "couldn't check" stay distinguishable.
    """
    today = utc_today()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            rows = await query_layer(
                client, FISH_KILL_SERVICE, 0,
                where=since("observation_date", today - timedelta(days=LOOKBACK_DAYS)),
                **within_miles_of_river_bend(RADIUS_MI),
            )
    except Exception as e:
        logger.warning("NC DEQ fish kill / algal bloom fetch failed: %s", e)
        return None

    incidents = []
    for row in rows:
        observed = epoch_ms_to_date(row.get("observation_date"))
        if observed is None:
            continue
        report_type = row.get("report_type") or ""
        fish_count = row.get("fish_kill_number")
        incidents.append({
            "id": row.get("incident_id"),
            "type": report_type,
            "fish_kill": "Fish Kill" in report_type,
            "algal_bloom": "Algal Bloom" in report_type,
            "date": observed.isoformat(),
            "age_days": (today - observed).days,
            "waterbody": _text(row.get("waterbody")),
            "location": _text(row.get("nearby_landmarks")),
            "fish_count": int(fish_count) if fish_count else None,
            "investigation_status": _text(row.get("investigation_status")),
            "findings": _text(row.get("final_investigation_comments")),
            "distance_mi": _distance(row),
        })

    incidents.sort(key=lambda i: i["date"], reverse=True)
    return incidents


async def fetch_sewer_spills() -> list[dict] | None:
    """
    Sanitary sewer overflows reported to NC DEQ near River Bend in the last
    LOOKBACK_DAYS, newest first. A spill that reached surface water is the
    most direct bacteria signal there is short of an actual water sample.
    Returns None if the feed is unreachable.
    """
    today = utc_today()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            rows = await query_layer(
                client, SSO_SERVICE, 0,
                where=since("dwr_start_date", today - timedelta(days=LOOKBACK_DAYS)),
                **within_miles_of_river_bend(RADIUS_MI),
            )
    except Exception as e:
        logger.warning("NC DEQ sewer overflow fetch failed: %s", e)
        return None

    spills = []
    for row in rows:
        started = epoch_ms_to_date(row.get("dwr_start_date"))
        if started is None:
            continue
        # Operators file an initial 24h report, then a 5-day report with
        # corrected figures — prefer the 5-day values when present.
        permit = _text(row.get("dwr_permit_with_name"))
        spills.append({
            "id": row.get("dwr_incident_number"),
            "date": started.isoformat(),
            "age_days": (today - started).days,
            "system": permit.split(" - ", 1)[-1] if permit else None,
            "location": _text(row.get("deq_address")),
            "volume_gal": row.get("dwr_volume_5d") or row.get("dwr_volume"),
            "volume_reached_water_gal": (
                row.get("dwr_volume_waterbody_5d") or row.get("dwr_volume_waterbody")
            ),
            "reached_water": _yes(row.get("dwr_reached_water")) or _yes(row.get("dwr_reached_waterbody_5d")),
            "waterbody": _text(row.get("dwr_waterbody_5d")) or _text(row.get("dwr_waterbody")),
            "ongoing": _yes(row.get("dwr_ongoing")),
            "cause": _text(row.get("dwr_cause_5d")),
            "distance_mi": _distance(row, "deq_latitude", "deq_longitude") or _distance(row),
        })

    spills.sort(key=lambda s: s["date"], reverse=True)
    return spills
