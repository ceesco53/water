import asyncio
import logging
from datetime import date

import httpx

logger = logging.getLogger(__name__)

USGS_BASE = "https://waterservices.usgs.gov/nwis/iv/"
USGS_STAT_BASE = "https://waterservices.usgs.gov/nwis/stat/"

STATIONS = {
    "02092500": "Trent River near Trenton (upstream)",
    "02092554": "Trent River at Pollocksville (closest active gauge)",
    # 02092558 omitted — inactive since 1961, water-quality samples only, no real-time data
    # 02092576 (Hwy 70, New Bern) omitted — stopped reporting 2020-08-06; its only ever
    # parameter (62620, estuary water-surface elevation) isn't one this app reads anyway
}

PARAM_NAMES = {
    "00060": "discharge_cfs",
    "00065": "gage_height_ft",
    "00010": "water_temp_c",
}

# Site + parameter the scoring model uses as the upstream runoff signal.
DISCHARGE_SITE = "02092500"
DISCHARGE_PARAM = "00060"


async def fetch_usgs_data() -> dict:
    params = {
        "format": "json",
        "sites": ",".join(STATIONS.keys()),
        "parameterCd": "00060,00065,00010",
        "period": "P7D",
    }

    async def _fetch_iv() -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(USGS_BASE, params=params)
            resp.raise_for_status()
            return resp.json()

    try:
        data, p80 = await asyncio.gather(_fetch_iv(), fetch_discharge_p80(DISCHARGE_SITE))
    except Exception as e:
        logger.error(f"USGS API failed: {e}")
        return {}

    result: dict = {}

    for ts in data.get("value", {}).get("timeSeries", []):
        site_code = ts["sourceInfo"]["siteCode"][0]["value"]
        var_code = ts["variable"]["variableCode"][0]["value"]
        param_name = PARAM_NAMES.get(var_code, var_code)

        values = ts.get("values", [{}])[0].get("value", [])
        valid_values = [
            float(v["value"])
            for v in values
            if v.get("value") and v["value"] not in ("-999999", "")
        ]

        if site_code not in result:
            result[site_code] = {
                "site_name": STATIONS.get(site_code, site_code),
                "site_code": site_code,
            }

        if valid_values:
            result[site_code][param_name] = valid_values[-1]

    if p80 is not None and DISCHARGE_SITE in result:
        result[DISCHARGE_SITE]["discharge_cfs_p80"] = p80

    return result


async def fetch_discharge_p80(site_code: str) -> float | None:
    """
    Historical (period-of-record) 80th-percentile discharge for today's
    month/day, from USGS's statistics service: "today's flow is higher than
    80% of everything recorded on this calendar day across N years of record."

    This replaced a rolling 80th-percentile computed from just the trailing
    7 days of live readings, which is self-referential — a below-normal week
    that ticks up partway through gets called "elevated" relative to itself,
    and a week that's uniformly high (e.g. a multi-day flood) never crosses
    its own 80th percentile at all. Comparing against the actual seasonal
    baseline avoids both failure modes.
    """
    today = date.today()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                USGS_STAT_BASE,
                params={
                    "format": "rdb",
                    "sites": site_code,
                    "statReportType": "daily",
                    "statTypeCd": "p80",
                    "parameterCd": DISCHARGE_PARAM,
                },
            )
            resp.raise_for_status()
            text = resp.text
    except Exception as e:
        logger.warning("USGS stat service failed for %s: %s", site_code, e)
        return None

    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    if len(lines) < 3:
        return None

    header = lines[0].split("\t")
    try:
        month_idx = header.index("month_nu")
        day_idx = header.index("day_nu")
        p80_idx = header.index("p80_va")
    except ValueError:
        return None

    for row in lines[2:]:  # lines[1] is the RDB format-code row (e.g. "5s\t15s\t...")
        cols = row.split("\t")
        if len(cols) <= max(month_idx, day_idx, p80_idx):
            continue
        try:
            if int(cols[month_idx]) == today.month and int(cols[day_idx]) == today.day:
                return float(cols[p80_idx])
        except (ValueError, IndexError):
            continue

    return None
