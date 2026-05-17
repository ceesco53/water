import asyncio
import csv
import io
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

WQP_BASE = "https://www.waterqualitydata.us"

# Both NC BEACH Program sites covering the Trent/Neuse corridor near River Bend
SITES = {
    "21NCBCH-C100A": "Neuse R. at Union Point (C100A)",  # mouth of Trent — closest
    "21NCBCH-C99":   "Neuse R. at NW Creek (C99)",       # ~4mi downstream
}

# NC BEACH Act freshwater Enterococcus thresholds (MPN/100mL)
# Source: EPA 2012 Recreational Water Quality Criteria
_SAFE_LIMIT = 35
_UNSAFE_LIMIT = 130
_STALE_DAYS = 14

_STATUS_RANK = {"unsafe": 3, "caution": 2, "safe": 1, "unknown": 0}


def _classify(value_mpn: float, age_days: int) -> str:
    if value_mpn > _UNSAFE_LIMIT:
        return "unsafe"
    if value_mpn > _SAFE_LIMIT or age_days > _STALE_DAYS:
        return "caution"
    return "safe"


async def _fetch_site(client: httpx.AsyncClient, site_id: str) -> list[dict]:
    try:
        resp = await client.get(
            f"{WQP_BASE}/data/Result/search",
            params={
                "siteid": site_id,
                "characteristicName": "Enterococcus",
                "mimeType": "csv",
                "sorted": "yes",
                "startDateLo": "01-01-2024",
            },
        )
        resp.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        records = []
        for row in rows:
            date_str = row.get("ActivityStartDate", "")
            value_str = row.get("ResultMeasureValue", "")
            if date_str and value_str:
                try:
                    records.append({
                        "date": datetime.strptime(date_str, "%Y-%m-%d"),
                        "value": float(value_str),
                    })
                except (ValueError, TypeError):
                    pass
        return records
    except Exception as e:
        logger.error("EPA WQP fetch failed for %s: %s", site_id, e)
        return []


async def fetch_bacteria_wqp() -> dict:
    """
    Fetch Enterococcus from EPA WQP for NC BEACH stations C100A (Union Point,
    mouth of Trent) and C99 (NW Creek). Returns worst-of status across both sites.
    """
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=15.0) as client:
        results = await asyncio.gather(
            *[_fetch_site(client, sid) for sid in SITES],
            return_exceptions=True,
        )

    beaches = []
    worst_status = "unknown"
    worst_mpn: float | None = None
    worst_date: str | None = None
    worst_age: int | None = None

    for site_id, site_name, records in zip(SITES.keys(), SITES.values(), results):
        if isinstance(records, Exception) or not records:
            continue
        latest = records[-1]
        age_days = (now - latest["date"].replace(tzinfo=timezone.utc)).days
        status = _classify(latest["value"], age_days)
        beaches.append({
            "id": site_id,
            "name": site_name,
            "status": status,
            "status_code": None,
            "latest_mpn": latest["value"],
            "latest_date": latest["date"].strftime("%Y-%m-%d"),
            "age_days": age_days,
        })
        if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(worst_status, 0):
            worst_status = status
            worst_mpn = latest["value"]
            worst_date = latest["date"].strftime("%Y-%m-%d")
            worst_age = age_days

    if not beaches:
        return {
            "status": "unknown",
            "beaches": [],
            "source": "EPA WQP",
            "source_url": "https://www.waterqualitydata.us/",
        }

    return {
        "status": worst_status,
        "beaches": beaches,
        "source_url": "https://www.waterqualitydata.us/",
        "source": "EPA WQP / NC BEACH Program",
        "latest_mpn": worst_mpn,
        "latest_date": worst_date,
        "age_days": worst_age,
    }
