import csv
import io
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

WQP_BASE = "https://www.waterqualitydata.us"
C99_SITE = "21NCBCH-C99"
C99_NAME = "Neuse R. near NW Creek (C99)"

# NC BEACH Act freshwater Enterococcus thresholds (MPN/100mL)
# Source: EPA 2012 Recreational Water Quality Criteria
_SAFE_LIMIT = 35
_UNSAFE_LIMIT = 130
_STALE_DAYS = 14


def _classify(value_mpn: float, age_days: int) -> str:
    if value_mpn > _UNSAFE_LIMIT:
        return "unsafe"
    if value_mpn > _SAFE_LIMIT or age_days > _STALE_DAYS:
        return "caution"
    return "safe"


async def fetch_bacteria_wqp() -> dict:
    """
    Fetch Enterococcus data from EPA Water Quality Portal for NC BEACH station C99.
    Nearest monitored site to River Bend on the Neuse/Trent system.
    """
    params = {
        "siteid": C99_SITE,
        "characteristicName": "Enterococcus",
        "mimeType": "csv",
        "sorted": "yes",
        "startDateLo": "01-01-2024",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{WQP_BASE}/data/Result/search", params=params)
            resp.raise_for_status()
            text = resp.text
    except Exception as e:
        logger.error("EPA WQP bacteria fetch failed: %s", e)
        return {
            "status": "unknown",
            "beaches": [],
            "source": "EPA WQP",
            "source_url": "https://www.waterqualitydata.us/",
        }

    records = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        date_str = row.get("ActivityStartDate", "")
        value_str = row.get("ResultMeasureValue", "")
        unit = row.get("ResultMeasure/MeasureUnitCode", "MPN")
        if date_str and value_str:
            try:
                sample_date = datetime.strptime(date_str, "%Y-%m-%d")
                records.append(
                    {
                        "date": sample_date,
                        "value": float(value_str),
                        "unit": unit or "MPN",
                    }
                )
            except (ValueError, TypeError):
                continue

    if not records:
        return {
            "status": "unknown",
            "beaches": [],
            "source": "EPA WQP",
            "source_url": "https://www.waterqualitydata.us/",
        }

    latest = records[-1]  # sorted ascending — last is most recent
    now = datetime.now(timezone.utc)
    age_days = (now - latest["date"].replace(tzinfo=timezone.utc)).days
    status = _classify(latest["value"], age_days)

    return {
        "status": status,
        "beaches": [
            {
                "id": C99_SITE,
                "name": C99_NAME,
                "status": status,
                "status_code": None,
            }
        ],
        "source_url": "https://www.waterqualitydata.us/",
        "source": "EPA WQP / NC BEACH Program",
        "latest_mpn": latest["value"],
        "latest_date": latest["date"].strftime("%Y-%m-%d"),
        "age_days": age_days,
    }
