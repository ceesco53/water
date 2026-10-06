import functools
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# USGS's modernized Water Data API. The legacy waterservices.usgs.gov (NWIS
# iv/stat services) this app used before is decommissioned in Q1 2027, with
# intentional slowdowns and scheduled outages permitted from August 2026 on.
# Works without an API key at this app's request rate.
USGS_LATEST = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"

STATIONS = {
    "02092500": "Trent River near Trenton (upstream)",
    "02092554": "Trent River at Pollocksville (closest active gauge)",
    # 02092558 omitted — inactive since 1961, water-quality samples only, no real-time data
    # 02092576 (Hwy 70, New Bern) omitted — stopped reporting 2020-08-06; its only ever
    # parameter (62620, estuary water-surface elevation) isn't one this app reads anyway
}

# No water-temperature sensor (00010) is active at any USGS site within ~50
# miles of River Bend — checked 2026-10 — so temperature comes from elsewhere.
PARAM_NAMES = {
    "00060": "discharge_cfs",
    "00065": "gage_height_ft",
}

# latest-continuous returns each time series' newest value however old it is
# — Pollocksville's discharge sensor was retired in 2008 and its last reading
# still comes back. Anything older than this is a dead sensor, not "current".
_MAX_READING_AGE = timedelta(hours=24)

# Site the scoring model uses as the upstream runoff signal.
DISCHARGE_SITE = "02092500"
_P80_FILE = Path(__file__).resolve().parent.parent / "data" / "trenton_discharge_p80.json"


async def fetch_usgs_data() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                USGS_LATEST,
                params={
                    "f": "json",
                    "monitoring_location_id": ",".join(f"USGS-{s}" for s in STATIONS),
                    "parameter_code": ",".join(PARAM_NAMES),
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("USGS API failed: %s", e)
        return {}

    now = datetime.now(timezone.utc)
    result: dict = {}

    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        site_code = (props.get("monitoring_location_id") or "").removeprefix("USGS-")
        param_name = PARAM_NAMES.get(props.get("parameter_code"))
        if site_code not in STATIONS or param_name is None:
            continue

        entry = result.setdefault(site_code, {
            "site_name": STATIONS[site_code],
            "site_code": site_code,
        })

        try:
            ts = datetime.fromisoformat(props["time"])
            value = float(props["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if now - ts > _MAX_READING_AGE:
            continue
        entry[param_name] = value

    p80 = discharge_p80(date.today())
    if p80 is not None and DISCHARGE_SITE in result:
        result[DISCHARGE_SITE]["discharge_cfs_p80"] = p80

    return result


@functools.cache
def _p80_table() -> dict[str, float]:
    with open(_P80_FILE) as f:
        return json.load(f)["p80_cfs"]


def discharge_p80(day: date) -> float | None:
    """
    Historical (period-of-record) 80th-percentile discharge at Trenton for
    this calendar day: "today's flow is higher than 80% of everything
    recorded on this date across 76 years of record."

    The day-of-year table is a snapshot of the legacy USGS statistics
    service, which has no equivalent in the new Water Data API. A 76-year
    percentile barely moves year to year, so a static table is accurate —
    regenerate it from the new API's `daily` collection if it ever needs
    refreshing.

    This replaced a rolling 80th percentile of just the trailing 7 days,
    which is self-referential — a quiet week that ticks up reads as
    "elevated", and a uniformly high week (a multi-day flood) never crosses
    its own 80th percentile at all.
    """
    try:
        return _p80_table().get(day.strftime("%m-%d"))
    except (OSError, ValueError, KeyError) as e:
        logger.warning("USGS p80 table unreadable: %s", e)
        return None
