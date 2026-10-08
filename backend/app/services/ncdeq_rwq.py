import asyncio
import logging
import math

import httpx

from ..geo import miles_from_home
from .arcgis import epoch_ms_to_date, query_layer, utc_today

logger = logging.getLogger(__name__)

# NC DEQ Recreational Water Quality program — the feature service behind
# DEQ's own swimming-advisory map. Replaces the EPA Water Quality Portal copy
# of the same samples, which lags DEQ's own publication by 5+ weeks.
SERVICE = "PUBLICVIEWRecreationWaterQualityDatabase"
_STATIONS_LAYER = 0  # one row per site, with DEQ's posted advisory Status
_SAMPLES_LAYER = 1   # one row per sample: MPN, salinity, water temp
SOURCE_URL = "https://ncdenr.maps.arcgis.com/apps/dashboards/99430d6fd1824b78ae328c6a5538852f"

# Stations covering the Trent/Neuse corridor near River Bend, closest first,
# with the water each samples (see soundrivers.TARGET_SITES for the reaches).
# Sampled weekly-to-biweekly April–September, twice in October, and monthly
# November–March — so unlike Sound Rivers, there's data year-round.
SITES = {
    "C100A": "Union Point, New Bern (mouth of the Trent)",
    "C99": "NW Creek, Fairfield Harbor",
}
REACH = {"C100A": "trent", "C99": "neuse"}

# 15A NCAC 18A .3402 enterococcus standards (per 100 mL): a single sample at
# or above 104 exceeds the standard at Tier I and II sites; Tier I sites also
# fail on a 30-day geometric mean at or above 35. Both sites above are Tier II,
# but River Bend residents swim often, so the Tier I geomean test is applied
# too — as "caution" only, since it isn't these sites' legal standard.
_SINGLE_SAMPLE_LIMIT = 104
_GEOMEAN_LIMIT = 35
_GEOMEAN_WINDOW_DAYS = 30

# DEQ's posted advisory (the station layer's Status field, a coded domain).
_OFFICIAL_STATUS = {
    "Advisory": "unsafe",
    "Pending Swimming Advisory": "caution",  # exceeded once; resample pending
    "Precautionary": "caution",              # issued after heavy rain, before sampling
    "No Advisory": "safe",
}

_STATUS_RANK = {"unsafe": 3, "caution": 2, "safe": 1, "unknown": 0}


def _num(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _sample_status(mpn: float, geomean: float | None) -> str:
    if mpn >= _SINGLE_SAMPLE_LIMIT:
        return "unsafe"
    if geomean is not None and geomean >= _GEOMEAN_LIMIT:
        return "caution"
    return "safe"


async def fetch_ncdeq_rwq() -> list[dict]:
    """
    Latest enterococcus reading per site, as bacteria readings in the same
    shape soundrivers.py produces. Each site's status is the worse of DEQ's
    posted advisory and what the samples themselves show (an advisory can
    trail a bad sample by a day or two).
    """
    asn_list = ",".join(f"'{asn}'" for asn in SITES)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            stations, samples = await asyncio.gather(
                query_layer(
                    client, SERVICE, _STATIONS_LAYER,
                    where=f"ASN IN ({asn_list})",
                    outFields="ASN,Status,LATITUDE,LONGITUDE",
                ),
                query_layer(
                    client, SERVICE, _SAMPLES_LAYER,
                    where=f"ASN IN ({asn_list}) AND CharacteristicName = 'Enterococcus'",
                    outFields="ASN,Date,MPN,Salinity,Water_Temp",
                    orderByFields="Date DESC",
                    # ~3 months of biweekly sampling across both sites — enough
                    # for the latest sample plus its 30-day geomean window.
                    resultRecordCount=50,
                ),
            )
    except Exception as e:
        logger.warning("NC DEQ recreational water quality fetch failed: %s", e)
        return []

    advisories = {s.get("ASN"): s.get("Status") for s in stations}
    distances = {
        s.get("ASN"): round(miles_from_home(s["LATITUDE"], s["LONGITUDE"]), 1)
        for s in stations
        if s.get("LATITUDE") is not None and s.get("LONGITUDE") is not None
    }

    by_site: dict[str, list[tuple]] = {}
    for row in samples:
        sample_date = epoch_ms_to_date(row.get("Date"))
        mpn = _num(row.get("MPN"))
        if sample_date is None or mpn is None:
            continue
        by_site.setdefault(row.get("ASN"), []).append((sample_date, mpn, row))

    today = utc_today()
    readings = []
    for asn, name in SITES.items():
        rows = sorted(by_site.get(asn, []), key=lambda r: r[0], reverse=True)
        if not rows:
            continue
        latest_date, latest_mpn, latest_row = rows[0]

        window = [m for d, m, _ in rows if (latest_date - d).days < _GEOMEAN_WINDOW_DAYS]
        geomean = (
            math.exp(sum(math.log(max(m, 1.0)) for m in window) / len(window))
            if len(window) >= 2
            else None
        )

        advisory = advisories.get(asn)
        status = max(
            _sample_status(latest_mpn, geomean),
            _OFFICIAL_STATUS.get(advisory, "unknown"),
            key=lambda s: _STATUS_RANK[s],
        )

        readings.append({
            "source": "NC DEQ",
            "site_id": asn,
            "site_name": name,
            "reach": REACH[asn],
            "distance_mi": distances.get(asn),
            "status": status,
            "advisory": advisory,
            "sample_date": latest_date.isoformat(),
            "age_days": (today - latest_date).days,
            "mpn": latest_mpn,
            "geomean_mpn": round(geomean) if geomean is not None else None,
            "salinity_ppt": _num(latest_row.get("Salinity")),
            "water_temp_f": _num(latest_row.get("Water_Temp")),
            "source_url": SOURCE_URL,
        })

    return readings
