"""
Step 2 of score calibration: build the training set.

One row per NC DEQ enterococcus sample at Union Point (C100A) and NW Creek
(C99), 1997 onward, with what the dashboard could have known *before* the
sample was drawn:

  rain_24h/48h/72h/7d  KEWN rainfall over windows ending at the sample's local
                       time, from the Iowa Environmental Mesonet's archive of
                       KEWN's routine :54 METARs -- the same hourly totals the
                       live dashboard sums
  flow_cfs, flow_p80   Trent River at Trenton: the previous day's mean
                       discharge (the live app reads the instantaneous value)
                       and the day-of-year 80th percentile the app compares
                       it to
  prev_*               the site's previous sample, since a sample's own
                       salinity and temperature aren't known until it's taken

  kewn_/mrms_/stage4_   daily rain the 3 full days before the sample day (d1_3)
  d1_3, d4_7           and the 4 before those (d4_7), from KEWN and from radar
                       at the site (IEM; 2014 on) -- see compare_rain.py

Candidate predictors, tested in test_predictors.py:
  wind_ne_24h/72h      mean KEWN wind speed (kt) along the northeast direction
                       that pushes Sound water up the Trent; wind_speed_24h
  level_plln_24h,      Trent River at Pollocksville gauge height over the prior
  level_plln_change_3d 24h, and its change from 3 days earlier (USGS, 2007 on)
  dry_days_before      dry days (<0.1") before the 72h rain window, capped at 30
  tide_ft,             NOAA's predicted tide at Oriental at sample time, and
  tide_range_day       that day's range (spring vs neap tides)

Labels: mpn, and exceeds = mpn >= 104 (NC's single-sample standard). The
sample's own salinity/temperature are kept as obs_* for analysis only --
using them as predictors would leak the answer.

Rain QA: METARs omit the precipitation group in hours without rain, which
older IEM records show as "M", so those count as zero. To catch real gauge
outages, hourly totals are checked against NOAA's daily record for the same
station: per year (rain_year_ratio) and over the 3 full days before each
sample (rain_check: ok / mismatch / unverified where NOAA has gaps). Each
window's share of hours with any report is kept too (rain_coverage_7d).

Run from backend/ with Python 3.11+:
    pip install -r calibration/requirements.txt
    python -m calibration.build_dataset

Completed years of hourly rain are cached in calibration/.cache/; everything
else is refetched each run. Writes calibration/data/samples.csv.
"""
import bisect
import csv
import io
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from itertools import accumulate
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from app.services.arcgis import NCDEQ_ARCGIS
from app.services.ncdeq_rwq import SERVICE as DEQ_SERVICE, SITES
from app.services.usgs import DISCHARGE_SITE, discharge_p80

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"
OUT = HERE / "data" / "samples.csv"

LOCAL = ZoneInfo("America/New_York")
EXCEEDANCE_MPN = 104  # 15A NCAC 18A .3402 single-sample standard
DEQ_SAMPLES_LAYER = 1

IEM_ASOS = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
NCEI_DAILY = "https://www.ncei.noaa.gov/access/services/data/v1"
KEWN_GHCN_ID = "USW00093719"  # New Bern Coastal Carolina Regional Airport
USGS_DAILY = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items"
IEMRE_MULTIDAY = "https://mesonet.agron.iastate.edu/iemre/multiday/{start}/{end}/{lat:.4f}/{lon:.4f}/json"
RADAR_FIRST_YEAR = 2014  # MRMS daily totals in IEMRE start here

USGS_CONTINUOUS = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"
POLLOCKSVILLE = "02092554"   # Trent River gauge height, 15-min, 2007 on
LEVEL_FIRST_YEAR = 2007
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
TIDE_STATION = "8655133"     # Oriental, Neuse River: nearest NOAA tide prediction station
# Wind from this compass direction pushes Pamlico Sound water up the Neuse
# and into the Trent; the wind_ne_* features measure speed along it.
SETUP_WIND_FROM_DEG = 45

# DEQ station coordinates (stations layer), for radar rain at each site
SITE_COORDS = {"C100A": (35.1031, -77.0349), "C99": (35.0646, -76.9702)}

RAIN_WINDOWS_H = {"rain_24h": 24, "rain_48h": 48, "rain_72h": 72, "rain_7d": 168}

# Samples are drawn mid-morning; when a record has no usable time, assume 10am.
_DEFAULT_SAMPLE_TIME = (10, 0)
_TIME_RE = re.compile(r"(\d{1,2}):?(\d{2})")


def _num(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return math.nan
    return v


# ── NC DEQ samples ───────────────────────────────────────────────────────────

def _sampled_at(text_date: str, time_str) -> tuple[datetime, bool]:
    """TextDate is 'M-DD-YYYY' (a couple of rows: 'MMDDYYYY'); Time is local clock time, 'HH:MM'."""
    if "-" in text_date:
        month, day, year = (int(p) for p in text_date.split("-"))
    else:
        month, day, year = int(text_date[:2]), int(text_date[2:4]), int(text_date[4:])
    m = _TIME_RE.fullmatch((time_str or "").strip())
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        hh, mm, assumed = int(m.group(1)), int(m.group(2)), False
    else:
        (hh, mm), assumed = _DEFAULT_SAMPLE_TIME, True
    return datetime(year, month, day, hh, mm, tzinfo=LOCAL), assumed


def fetch_deq_samples(client: httpx.Client) -> pd.DataFrame:
    asn_list = ",".join(f"'{asn}'" for asn in SITES)
    rows, offset = [], 0
    while True:
        resp = client.get(
            f"{NCDEQ_ARCGIS}/{DEQ_SERVICE}/FeatureServer/{DEQ_SAMPLES_LAYER}/query",
            params={
                "f": "json",
                "returnGeometry": "false",
                "where": f"ASN IN ({asn_list}) AND CharacteristicName = 'Enterococcus'",
                "outFields": "ASN,TextDate,Time,MPN,Salinity,Water_Temp,Rainfall_Amt",
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": 1000,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"DEQ samples query failed: {data['error']}")
        batch = [f["attributes"] for f in data.get("features", [])]
        rows += batch
        if not data.get("exceededTransferLimit") or not batch:
            break
        offset += len(batch)

    records = []
    for r in rows:
        if r.get("MPN") is None or not r.get("TextDate"):
            continue
        sampled_at, assumed = _sampled_at(r["TextDate"], r.get("Time"))
        deq_rain = (r.get("Rainfall_Amt") or "").strip().upper()
        records.append({
            "site": r["ASN"],
            "sampled_at": sampled_at,
            "time_assumed": assumed,
            "mpn": float(r["MPN"]),
            "obs_salinity": _num(r.get("Salinity")),
            "obs_water_temp": _num(r.get("Water_Temp")),
            # What the sampler wrote down for recent rain; kept to cross-check KEWN
            "deq_rainfall_in": 0.0 if deq_rain == "TRACE" else _num(deq_rain),
        })
    return pd.DataFrame.from_records(records)


# ── KEWN hourly rain (IEM) ───────────────────────────────────────────────────

def _iem_year(client: httpx.Client, year: int) -> str:
    cache = CACHE / f"kewn_p01i_{year}.csv"
    if cache.exists():
        return cache.read_text()
    resp = client.get(IEM_ASOS, params={
        "station": "EWN", "data": "p01i",
        "year1": year, "month1": 1, "day1": 1,
        "year2": year + 1, "month2": 1, "day2": 1,
        "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no",
        "missing": "M", "trace": "T", "direct": "no",
        "report_type": 3,  # routine hourly METARs only
    })
    resp.raise_for_status()
    text = resp.text
    if year < datetime.now(timezone.utc).year:  # completed years don't change
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(text)
    else:
        time.sleep(1)  # be polite to IEM between uncached requests
    return text


def fetch_kewn_hourly(client: httpx.Client, first_year: int, last_year: int) -> tuple[list[datetime], list[float]]:
    obs: dict[datetime, float] = {}
    for year in range(first_year, last_year + 1):
        for row in csv.DictReader(io.StringIO(_iem_year(client, year))):
            ts = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            value = row.get("p01i", "M")
            obs[ts] = 0.0 if value in ("M", "T", "") else float(value)
    times = sorted(obs)
    return times, [obs[t] for t in times]


def fetch_ghcn_daily(client: httpx.Client, start: date, end: date) -> dict[date, float]:
    resp = client.get(NCEI_DAILY, params={
        "dataset": "daily-summaries", "stations": KEWN_GHCN_ID, "dataTypes": "PRCP",
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "units": "standard", "format": "json",
    })
    resp.raise_for_status()
    out = {}
    for row in resp.json():
        v = _num(row.get("PRCP"))
        if not math.isnan(v):
            out[date.fromisoformat(row["DATE"])] = v
    return out


# ── Trent River flow (USGS) ──────────────────────────────────────────────────

def fetch_trenton_daily(client: httpx.Client, start: date, end: date) -> dict[date, float]:
    url = USGS_DAILY
    params: dict | None = {
        "f": "json",
        "monitoring_location_id": f"USGS-{DISCHARGE_SITE}",
        "parameter_code": "00060",
        "statistic_id": "00003",  # daily mean
        "datetime": f"{start.isoformat()}/{end.isoformat()}",
        "limit": 10000,
    }
    flows: dict[date, float] = {}
    while url:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        for feature in data.get("features", []):
            props = feature.get("properties") or {}
            v = _num(props.get("value"))
            if not math.isnan(v) and props.get("time"):
                flows[date.fromisoformat(props["time"][:10])] = v
        url = next((link["href"] for link in data.get("links", []) if link.get("rel") == "next"), None)
        params = None
    return flows


# ── Radar rain at each site (IEM) ────────────────────────────────────────────

def fetch_site_radar(client: httpx.Client, site: str, first_year: int, last_year: int) -> dict[date, dict]:
    """
    Daily radar rain at a DEQ site: MRMS (radar, gauge-corrected) and IEMRE's
    Stage IV-based total. Lets compare_rain test whether rain *at the site*
    predicts exceedances better than KEWN's gauge miles away.
    """
    lat, lon = SITE_COORDS[site]
    out: dict[date, dict] = {}
    for year in range(max(first_year, RADAR_FIRST_YEAR), last_year + 1):
        cache = CACHE / f"radar_{site}_{year}.json"
        if cache.exists():
            text = cache.read_text()
        else:
            end = min(date(year, 12, 31), date.today())
            resp = client.get(IEMRE_MULTIDAY.format(start=f"{year}-01-01", end=end.isoformat(), lat=lat, lon=lon))
            resp.raise_for_status()
            text = resp.text
            if year < datetime.now(timezone.utc).year:
                CACHE.mkdir(parents=True, exist_ok=True)
                cache.write_text(text)
            time.sleep(1)
        for row in json.loads(text).get("data", []):
            out[date.fromisoformat(row["date"])] = {
                "mrms": _num(row.get("mrms_precip_in")),
                "stage4": _num(row.get("daily_precip_in")),
            }
    return out


# ── Candidate predictors (tested in test_predictors.py) ──────────────────────

def _cached_year(name: str, year: int, fetch) -> str:
    """Completed years never change; cache them. The current year is always refetched."""
    cache = CACHE / f"{name}_{year}.txt"
    if cache.exists():
        return cache.read_text()
    text = fetch()
    if year < datetime.now(timezone.utc).year:
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(text)
    else:
        time.sleep(1)
    return text


def fetch_kewn_wind(client: httpx.Client, first_year: int, last_year: int) -> list[tuple[datetime, float, float]]:
    """KEWN routine hourly wind: (time, speed kt, direction it blows FROM, degrees)."""
    out = []
    for year in range(first_year, last_year + 1):
        def fetch():
            resp = client.get(IEM_ASOS, params={
                "station": "EWN", "data": ["sknt", "drct"],
                "year1": year, "month1": 1, "day1": 1, "year2": year + 1, "month2": 1, "day2": 1,
                "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no", "missing": "M",
                "direct": "no", "report_type": 3,
            })
            resp.raise_for_status()
            return resp.text
        for row in csv.DictReader(io.StringIO(_cached_year("kewn_wind", year, fetch))):
            speed, direction = _num(row.get("sknt")), _num(row.get("drct"))
            if not math.isnan(speed) and not math.isnan(direction):
                ts = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                out.append((ts, speed, direction))
    return sorted(out)


def fetch_pollocksville_hourly(client: httpx.Client, first_year: int, last_year: int) -> dict[datetime, float]:
    """Trent River at Pollocksville gauge height, hourly means (ft)."""
    hourly: dict[datetime, list[float]] = {}
    for year in range(max(first_year, LEVEL_FIRST_YEAR), last_year + 1):
        def fetch():
            resp = client.get(USGS_CONTINUOUS, params={
                "f": "json", "monitoring_location_id": f"USGS-{POLLOCKSVILLE}", "parameter_code": "00065",
                "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
                "limit": 50000, "properties": "time,value",
            })
            resp.raise_for_status()
            return resp.text
        for f in json.loads(_cached_year("plln_stage", year, fetch)).get("features", []):
            v = _num(f["properties"].get("value"))
            if not math.isnan(v):
                t = datetime.fromisoformat(f["properties"]["time"]).replace(minute=0, second=0, microsecond=0)
                hourly.setdefault(t, []).append(v)
    return {t: sum(vs) / len(vs) for t, vs in hourly.items()}


def fetch_tide_predictions(client: httpx.Client, first_year: int, last_year: int) -> dict[datetime, float]:
    """NOAA's predicted astronomical tide at Oriental, hourly (ft above MLLW)."""
    out: dict[datetime, float] = {}
    for year in range(first_year, last_year + 1):
        def fetch():
            resp = client.get(COOPS, params={
                "station": TIDE_STATION, "product": "predictions", "datum": "MLLW", "interval": "h",
                "units": "english", "time_zone": "gmt", "format": "json",
                "begin_date": f"{year}0101", "end_date": f"{year}1231",
            })
            resp.raise_for_status()
            return resp.text
        for p in json.loads(_cached_year("tide_oriental", year, fetch)).get("predictions", []):
            out[datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)] = float(p["v"])
    return out


# ── Assembly ─────────────────────────────────────────────────────────────────

def build() -> pd.DataFrame:
    with httpx.Client(timeout=120.0, headers={"User-Agent": "water-monitor-calibration"}) as client:
        print("Fetching NC DEQ samples…")
        samples = fetch_deq_samples(client)
        first = samples["sampled_at"].min().date()
        last = samples["sampled_at"].max().date()
        print(f"  {len(samples)} samples, {first} to {last}")

        print("Fetching KEWN hourly rain (IEM)…")
        times, inches = fetch_kewn_hourly(client, first.year, last.year)
        print(f"  {len(times)} routine reports")

        print("Fetching KEWN daily rain (NOAA NCEI) for QA…")
        ghcn = fetch_ghcn_daily(client, date(first.year, 1, 1), last)

        print("Fetching Trenton daily discharge (USGS)…")
        flows = fetch_trenton_daily(client, first - timedelta(days=7), last)
        print(f"  {len(flows)} days")

        print("Fetching radar rain at each site (IEM)…")
        radar = {site: fetch_site_radar(client, site, first.year, last.year) for site in SITE_COORDS}

        print("Fetching candidate predictors: KEWN wind (IEM), Pollocksville stage (USGS), tides (NOAA)…")
        wind = fetch_kewn_wind(client, first.year, last.year)
        stage = fetch_pollocksville_hourly(client, first.year, last.year)
        tide = fetch_tide_predictions(client, first.year, last.year)
        print(f"  {len(wind)} wind obs, {len(stage)} stage hours, {len(tide)} tide hours")

    # Yearly QA: hourly-METAR totals vs NOAA's daily record for the station
    hourly_by_year: dict[int, float] = {}
    for t, v in zip(times, inches):
        y = t.astimezone(LOCAL).year
        hourly_by_year[y] = hourly_by_year.get(y, 0.0) + v
    ghcn_by_year: dict[int, float] = {}
    for d, v in ghcn.items():
        ghcn_by_year[d.year] = ghcn_by_year.get(d.year, 0.0) + v
    year_ratio = {
        y: hourly_by_year.get(y, 0.0) / ghcn_by_year[y]
        for y in ghcn_by_year if ghcn_by_year[y] > 0
    }
    print("\nRain QA — KEWN hourly METAR total vs NOAA daily total (inches):")
    for y in sorted(year_ratio):
        flag = "" if 0.85 <= year_ratio[y] <= 1.15 else "  <-- check"
        print(f"  {y}: {hourly_by_year.get(y, 0.0):6.2f} vs {ghcn_by_year[y]:6.2f}  ({year_ratio[y]:.0%}){flag}")

    # Per-sample QA: the 3 full days before each sample, hourly sum vs NOAA's
    # daily totals (which run midnight to midnight local standard time)
    hourly_by_lst_day: dict[date, float] = {}
    for t, v in zip(times, inches):
        d = (t - timedelta(hours=5)).date()
        hourly_by_lst_day[d] = hourly_by_lst_day.get(d, 0.0) + v

    def rain_check(local_day: date) -> str:
        days = [local_day - timedelta(days=k) for k in (1, 2, 3)]
        if any(d not in ghcn for d in days):
            return "unverified"
        hourly = sum(hourly_by_lst_day.get(d, 0.0) for d in days)
        daily = sum(ghcn[d] for d in days)
        return "ok" if abs(hourly - daily) <= max(0.15, 0.2 * max(hourly, daily)) else "mismatch"

    cum = [0.0, *accumulate(inches)]
    wind_times = [t for t, _, _ in wind]

    def window(end_utc: datetime, hours: int) -> tuple[float, int]:
        lo = bisect.bisect_right(times, end_utc - timedelta(hours=hours))
        hi = bisect.bisect_right(times, end_utc)
        return cum[hi] - cum[lo], hi - lo

    rows = []
    for s in samples.itertuples(index=False):
        end_utc = s.sampled_at.astimezone(timezone.utc)
        local_day = s.sampled_at.date()
        row = {
            "site": s.site,
            "sampled_at": s.sampled_at.isoformat(),
            "time_assumed": s.time_assumed,
            "year": local_day.year,
            "month": local_day.month,
            "doy": local_day.timetuple().tm_yday,
            "mpn": s.mpn,
            "log10_mpn": math.log10(max(s.mpn, 1.0)),
            "exceeds": s.mpn >= EXCEEDANCE_MPN,
        }
        for name, hours in RAIN_WINDOWS_H.items():
            total, _ = window(end_utc, hours)
            row[name] = round(total, 2)
        _, reports = window(end_utc, RAIN_WINDOWS_H["rain_7d"])
        row["rain_coverage_7d"] = round(reports / RAIN_WINDOWS_H["rain_7d"], 3)
        row["rain_year_ratio"] = round(year_ratio.get(local_day.year, math.nan), 3)
        row["rain_check"] = rain_check(local_day)

        # Daily-resolution rain for compare_rain: the 3 full days before the
        # sample day and the 4 before those, from KEWN and from radar at the site
        near = [local_day - timedelta(days=k) for k in (1, 2, 3)]
        far = [local_day - timedelta(days=k) for k in (4, 5, 6, 7)]
        row["kewn_d1_3"] = round(sum(hourly_by_lst_day.get(d, 0.0) for d in near), 2)
        row["kewn_d4_7"] = round(sum(hourly_by_lst_day.get(d, 0.0) for d in far), 2)
        site_radar = radar.get(s.site, {})
        for product in ("mrms", "stage4"):
            for name, days in (("d1_3", near), ("d4_7", far)):
                vals = [site_radar.get(d, {}).get(product) for d in days]
                ok = all(v is not None and not math.isnan(v) for v in vals)
                row[f"{product}_{name}"] = round(sum(vals), 2) if ok else math.nan

        # Candidate predictors -- all knowable before the sample is drawn
        for hours in (24, 72):
            recent = [(sp, dr) for t, sp, dr in wind[bisect.bisect_right(wind_times, end_utc - timedelta(hours=hours)):
                                                     bisect.bisect_right(wind_times, end_utc)]]
            row[f"wind_ne_{hours}h"] = (
                round(sum(sp * math.cos(math.radians(dr - SETUP_WIND_FROM_DEG)) for sp, dr in recent) / len(recent), 2)
                if len(recent) >= hours * 0.75 else math.nan
            )
        recent = [sp for t, sp, dr in wind[bisect.bisect_right(wind_times, end_utc - timedelta(hours=24)):
                                           bisect.bisect_right(wind_times, end_utc)]]
        row["wind_speed_24h"] = round(sum(recent) / len(recent), 2) if len(recent) >= 18 else math.nan

        hour = end_utc.replace(minute=0, second=0, microsecond=0)
        day_levels = [stage[hour - timedelta(hours=k)] for k in range(1, 25) if hour - timedelta(hours=k) in stage]
        earlier = [stage[hour - timedelta(hours=k)] for k in range(72, 97) if hour - timedelta(hours=k) in stage]
        row["level_plln_24h"] = round(sum(day_levels) / len(day_levels), 2) if len(day_levels) >= 18 else math.nan
        row["level_plln_change_3d"] = (
            round(row["level_plln_24h"] - sum(earlier) / len(earlier), 2)
            if len(earlier) >= 18 and not math.isnan(row["level_plln_24h"]) else math.nan
        )

        # Dry spell before the 72h window: consecutive days under 0.1" (cap 30)
        dry = 0
        while dry < 30 and hourly_by_lst_day.get(local_day - timedelta(days=4 + dry), 0.0) < 0.1:
            dry += 1
        row["dry_days_before"] = dry

        day_start = datetime.combine(local_day, datetime.min.time(), LOCAL).astimezone(timezone.utc)
        day_hours = [day_start + timedelta(hours=h) for h in range(24)]
        day_tides = [tide[t] for t in day_hours if t in tide]
        row["tide_ft"] = tide.get(hour, math.nan)
        row["tide_range_day"] = round(max(day_tides) - min(day_tides), 3) if len(day_tides) >= 20 else math.nan

        flow = flows.get(local_day - timedelta(days=1), math.nan)
        p80 = discharge_p80(local_day)
        row["flow_cfs"] = flow
        row["flow_p80"] = p80
        row["flow_ratio"] = round(flow / p80, 3) if p80 and not math.isnan(flow) else math.nan

        row["obs_salinity"] = s.obs_salinity
        row["obs_water_temp"] = s.obs_water_temp
        row["deq_rainfall_in"] = s.deq_rainfall_in
        rows.append(row)

    df = pd.DataFrame(rows).sort_values(["site", "sampled_at"]).reset_index(drop=True)

    # Previous sample at the same site -- known before this one is drawn
    by_site = df.groupby("site", sort=False)
    df["prev_mpn"] = by_site["mpn"].shift(1)
    df["prev_salinity"] = by_site["obs_salinity"].shift(1)
    df["prev_water_temp"] = by_site["obs_water_temp"].shift(1)
    prev_at = pd.to_datetime(by_site["sampled_at"].shift(1), utc=True)
    df["days_since_prev"] = (pd.to_datetime(df["sampled_at"], utc=True) - prev_at).dt.days

    return df


def main() -> None:
    df = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    n_ex = int(df["exceeds"].sum())
    print(f"\nWrote {OUT.relative_to(HERE.parent)}: {len(df)} samples, {n_ex} exceedances "
          f"({n_ex / len(df):.1%}); per site: "
          + ", ".join(f"{site} {int(g['exceeds'].sum())}/{len(g)}" for site, g in df.groupby("site")))
    print("Per-sample rain check (3 days before, hourly vs NOAA daily): "
          + ", ".join(f"{k} {v}" for k, v in df["rain_check"].value_counts().items()))


if __name__ == "__main__":
    main()
