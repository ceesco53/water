import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..geo import HOME_LAT, HOME_LON

logger = logging.getLogger(__name__)

# Radar-estimated rain at HOME: the Iowa Environmental Mesonet's IEMRE grid
# serves NCEP Stage IV hourly precipitation (radar, bias-corrected against
# rain gauges) for the cell containing a point. KEWN's gauge sits ~5.5 mi
# east of River Bend and has failed for weeks at a time; for the Oct 3-4,
# 2026 storm radar put ~2.2" over River Bend against KEWN's 1.4".
IEMRE_HOURLY = "https://mesonet.agron.iastate.edu/iemre/hourly/{day}/{lat:.4f}/{lon:.4f}/json"

# IEMRE fills hours Stage IV hasn't reached yet -- and future hours -- with
# IFS forecast values, so only hours ending at least this long ago count.
LATENCY_H = 3

_WINDOWS_H = {"radar_rain_24h_in": 24, "radar_rain_72h_in": 72, "radar_rain_7d_in": 168}

# Days old enough that Stage IV won't revise them, cached between refreshes
# (each refresh would otherwise be ~9 requests).
_SETTLED_AFTER = timedelta(days=2)
_day_cache: dict[date, list[tuple[datetime, float]]] = {}

_EMPTY = {**{k: None for k in _WINDOWS_H}, "radar_through": None}


async def _fetch_day(client: httpx.AsyncClient, day: date, now: datetime) -> list[tuple[datetime, float]]:
    if day in _day_cache:
        return _day_cache[day]
    resp = await client.get(IEMRE_HOURLY.format(day=day.isoformat(), lat=HOME_LAT, lon=HOME_LON))
    resp.raise_for_status()
    hours = []
    for row in resp.json().get("data", []):
        try:
            valid = datetime.fromisoformat(row["valid_utc"].replace("Z", "+00:00"))
            hours.append((valid, float(row["hourly_precip_in"])))
        except (KeyError, TypeError, ValueError):
            continue
    if now - datetime.combine(day, datetime.min.time(), timezone.utc) > _SETTLED_AFTER:
        _day_cache[day] = hours
    return hours


async def fetch_radar_rain() -> dict:
    """
    Radar rain totals at HOME over the 24h/72h/7d before `radar_through`
    (now minus LATENCY_H, rounded down to the hour). All None if any day in
    the window can't be fetched -- a partial window would read as drier.
    """
    now = datetime.now(timezone.utc)
    through = (now - timedelta(hours=LATENCY_H)).replace(minute=0, second=0, microsecond=0)
    start = through - timedelta(hours=max(_WINDOWS_H.values()))
    # IEMRE's day parameter is a local date; fetch a day either side of the
    # UTC span and keep hours by their UTC timestamps.
    days = [start.date() - timedelta(days=1) + timedelta(days=i)
            for i in range((through.date() - start.date()).days + 3)]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            per_day = await asyncio.gather(*(_fetch_day(client, d, now) for d in days))
    except Exception as e:
        logger.warning("IEM radar rain fetch failed: %s", e)
        return dict(_EMPTY)

    hourly = {valid: inches for day_hours in per_day for valid, inches in day_hours}
    totals = {}
    for name, hours in _WINDOWS_H.items():
        window_start = through - timedelta(hours=hours)
        in_window = [v for t, v in hourly.items() if window_start < t <= through]
        # Fewer hours than the window holds means a gap in IEM's grid
        totals[name] = round(sum(in_window), 2) if len(in_window) >= hours - 1 else None
    return {**totals, "radar_through": through.isoformat()}
