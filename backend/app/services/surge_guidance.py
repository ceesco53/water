import asyncio
import csv
import io
import logging
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# NWS Probabilistic Extra-Tropical Storm Surge (P-ETSS) guidance from the
# Meteorological Development Lab: tide + wind-driven surge + a correction from
# recent observations, hourly, ~4 days ahead, with 90%/10% exceedance levels.
# It's model guidance on a site NWS labels experimental -- not an official
# forecast, and not valid in tropical storms. No official (forecaster-issued)
# water-level forecast exists for the gauges near River Bend; the lower Trent
# isn't an NWS forecast point.
PETSS = "https://slosh.nws.noaa.gov/petss"

# master.csv maps NWS gauge IDs to P-ETSS station IDs; it rarely changes
_STATIONS_TTL = 24 * 3600
_stations: dict = {"map": None, "ts": 0.0}

_MISSING = 9999


async def _station_map(client: httpx.AsyncClient) -> dict[str, str]:
    if _stations["map"] is not None and time.time() - _stations["ts"] < _STATIONS_TTL:
        return _stations["map"]
    resp = await client.get(f"{PETSS}/datafiles/master.csv")
    resp.raise_for_status()
    mapping = {
        row["NWSLI"]: row["Station ID"]
        for row in csv.DictReader(io.StringIO(resp.text))
        if row.get("NWSLI") and row.get("Station ID")
    }
    _stations.update(map=mapping, ts=time.time())
    return mapping


def _parse_time(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


async def _station(client: httpx.AsyncClient, station_id: str) -> dict:
    resp = await client.post(f"{PETSS}/fixed/php/getData.php", data={"st": station_id})
    resp.raise_for_status()
    d = resp.json()
    obs, forecast = [], []
    for stamp, ob, twl, p90, p10 in zip(d["ts"], d["obs"], d["twl"], d["twl1"], d["twl2"]):
        if ob != _MISSING:
            obs.append((_parse_time(stamp), float(ob)))
        if twl != _MISSING:
            # twl1 is the level with a 90% chance of being exceeded (low end),
            # twl2 the 10% one (high end): together an 80%-likely range
            forecast.append((_parse_time(stamp), float(twl), float(p90), float(p10)))
    last_obs = max((t for t, _ in obs), default=None)
    return {
        "obs": obs,
        "forecast": [f for f in forecast if last_obs is None or f[0] > last_obs],
        "url": f"{PETSS}/index.php?stid={station_id}",
    }


async def fetch_surge_guidance(gauge_ids: list[str]) -> dict[str, dict]:
    """P-ETSS guidance for whichever of these NWS gauges it covers, keyed by gauge ID."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            mapping = await _station_map(client)
            covered = [(lid, mapping[lid]) for lid in gauge_ids if lid in mapping]
            run_resp = await client.get(f"{PETSS}/PDY.txt")
            results = await asyncio.gather(*(_station(client, sid) for _, sid in covered), return_exceptions=True)
    except Exception as e:
        logger.warning("P-ETSS guidance fetch failed: %s", e)
        return {}

    try:  # model cycle, e.g. "2026102306" = 06Z Oct 23
        run = datetime.strptime(run_resp.text.strip(), "%Y%m%d%H").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        run = None

    out = {}
    for (lid, _), result in zip(covered, results):
        if isinstance(result, Exception):
            logger.warning("P-ETSS guidance failed for %s: %s", lid, result)
        elif result["forecast"]:
            out[lid] = {**result, "run": run}
    return out
