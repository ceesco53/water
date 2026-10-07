import asyncio
import httpx
import math
import logging
import re
from datetime import datetime, timedelta, timezone

from ..geo import RIVER_BEND_LAT, RIVER_BEND_LON

logger = logging.getLogger(__name__)

NOAA_BASE = "https://api.weather.gov"
# Craven County Regional Airport (KEWN) — closest ASOS station to New Bern
NOAA_STATION = "KEWN"
# Minute past the hour KEWN sends its routine METAR; hourly precipitation
# resets right after it (see _fetch_rain_and_wind)
_ROUTINE_REPORT_MINUTE = 54
# River Bend's own 2.5km NWS grid cell — see _fetch_rain_forecast for why
NWS_GRID = "MHX/41,72"
NOAA_HEADERS = {
    "User-Agent": "(water-monitor/1.0, ceesco53@gmail.com)",
    "Accept": "application/geo+json",
}

# NOAA CO-OPS: Beaufort Duke Marine Lab (~40mi SE of New Bern)
# Closest station with real-time water temperature on the inner coast.
# No USGS sensor exists on any Trent River gauge (00010 unavailable at all 3 sites).
# Fallback only: main.py prefers the temperature NC DEQ measures on site when
# it samples Union Point, whenever that sample is under a week old.
COOPS_BASE = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
COOPS_WATER_TEMP_STATION = "8656483"
COOPS_WATER_TEMP_NAME = "Beaufort, NC (coastal proxy)"

_WIND_DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _deg_to_cardinal(degrees: float) -> str:
    return _WIND_DIRS[round(degrees / 22.5) % 16]


def _mm_to_in(mm: float) -> float:
    return mm / 25.4


async def fetch_water_temp_f() -> dict:
    """Fetch water temperature from NOAA CO-OPS Beaufort station."""
    from datetime import date, timedelta
    today = date.today().strftime("%Y%m%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                COOPS_BASE,
                params={
                    "station": COOPS_WATER_TEMP_STATION,
                    "product": "water_temperature",
                    "begin_date": yesterday,
                    "end_date": today,
                    "datum": "MLLW",
                    "time_zone": "lst_ldt",
                    "units": "english",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("NOAA CO-OPS water temp fetch failed: %s", e)
        return {"water_temp_f": None, "water_temp_source": None}

    readings = data.get("data", [])
    if not readings:
        logger.warning("NOAA CO-OPS water temp: no data returned")
        return {"water_temp_f": None, "water_temp_source": None}

    try:
        latest_f = float(readings[-1]["v"])
        return {
            "water_temp_f": round(latest_f, 1),
            "water_temp_source": COOPS_WATER_TEMP_NAME,
        }
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("NOAA CO-OPS water temp parse failed: %s", e)
        return {"water_temp_f": None, "water_temp_source": None}


async def fetch_weather_data() -> dict:
    rain_wind, water_temp, forecast, grid, alerts = await asyncio.gather(
        _fetch_rain_and_wind(),
        fetch_water_temp_f(),
        _fetch_rain_forecast(),
        _fetch_gridpoint_data(),
        fetch_nws_alerts(),
    )
    return {**rain_wind, **water_temp, **forecast, **grid, "alerts": alerts}


_SEVERITY_RANK = {"Extreme": 4, "Severe": 3, "Moderate": 2, "Minor": 1}


async def fetch_nws_alerts() -> list[dict] | None:
    """
    Active NWS alerts (warnings, watches, advisories) covering River Bend,
    most severe first. None if the API is unreachable, [] if all clear.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{NOAA_BASE}/alerts/active",
                params={"point": f"{RIVER_BEND_LAT},{RIVER_BEND_LON}"},
                headers=NOAA_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("NWS alerts fetch failed: %s", e)
        return None

    alerts = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if not props.get("event"):
            continue
        alerts.append({
            "event": props["event"],
            "severity": props.get("severity"),
            "headline": props.get("headline"),
            "ends": props.get("ends") or props.get("expires"),
        })
    alerts.sort(key=lambda a: _SEVERITY_RANK.get(a["severity"], 0), reverse=True)
    return alerts


_ISO_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?")


def _parse_valid_time(valid_time: str) -> tuple[datetime, datetime] | None:
    """NWS grid validTime is '<ISO start>/<ISO 8601 duration>', e.g. '2026-10-06T12:00:00+00:00/PT6H'."""
    try:
        start_str, duration = valid_time.split("/")
        start = datetime.fromisoformat(start_str)
    except ValueError:
        return None
    m = _ISO_DURATION.fullmatch(duration)
    if not m:
        return None
    days, hours, minutes = (int(g or 0) for g in m.groups())
    end = start + timedelta(days=days, hours=hours, minutes=minutes)
    return (start, end) if end > start else None


def _grid_values(props: dict, field: str):
    """Yield (start, end, value) for each valid interval of a raw grid field."""
    for v in (props.get(field) or {}).get("values", []):
        span = _parse_valid_time(v.get("validTime", ""))
        if span is not None and v.get("value") is not None:
            yield span[0], span[1], v["value"]


def _max_pct_within(props: dict, field: str, now: datetime, hours: int) -> int | None:
    horizon = now + timedelta(hours=hours)
    values = [
        value for start, end, value in _grid_values(props, field)
        if end > now and start < horizon
    ]
    return int(max(values)) if values else None


async def _fetch_gridpoint_data() -> dict:
    """
    Raw NWS grid data for River Bend's cell — the numbers behind the text
    forecast. Two things the text forecast can't give: how much rain is
    expected (a 60% chance of 0.05" is no runoff risk; 40% of 1.5" is), and
    the thunder probability over the next few hours — lightning being the
    most immediate swim hazard there is.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{NOAA_BASE}/gridpoints/{NWS_GRID}", headers=NOAA_HEADERS)
            resp.raise_for_status()
            props = resp.json().get("properties", {})
    except Exception as e:
        logger.warning("NWS gridpoint fetch failed: %s", e)
        return {"qpf_72h_in": None, "thunder_pct_6h": None, "thunder_pct_24h": None}

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=72)

    # QPF comes in 1–6h blocks; prorate the blocks that straddle now or the
    # 72h horizon by how much of each falls inside the window.
    qpf_mm = None
    for start, end, value in _grid_values(props, "quantitativePrecipitation"):
        overlap = (min(end, horizon) - max(start, now)).total_seconds()
        if overlap > 0:
            qpf_mm = (qpf_mm or 0.0) + value * overlap / (end - start).total_seconds()

    return {
        "qpf_72h_in": round(_mm_to_in(qpf_mm), 2) if qpf_mm is not None else None,
        "thunder_pct_6h": _max_pct_within(props, "probabilityOfThunder", now, 6),
        "thunder_pct_24h": _max_pct_within(props, "probabilityOfThunder", now, 24),
    }


async def _fetch_rain_forecast() -> dict:
    """
    Fetch NWS 7-day forecast for River Bend's own 2.5km grid cell and extract
    the peak precipitation probability within the next 72 hours. Used to give
    a forward-looking bacteria-risk warning (48–72h post-rain = peak
    contamination).

    Grid cell MHX/41,72 was resolved via api.weather.gov/points/35.0728,-77.1485
    (River Bend town hall). The previous MHX/45,74 is downtown New Bern at the
    Neuse/Trent confluence — a different grid cell, ~4mi away, whose forecast
    can diverge from River Bend's during the small-scale pop-up convection
    that drives most summer rain in coastal NC.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{NOAA_BASE}/gridpoints/{NWS_GRID}/forecast",
                headers=NOAA_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("NWS forecast fetch failed: %s", e)
        return {"rain_forecast_pct": None, "rain_forecast_period": None}

    periods = data.get("properties", {}).get("periods", [])
    # First 6 periods ≈ 72h (day + night alternating ~12h each)
    next_72h = periods[:6]

    peak_pct = 0
    peak_period_name = None
    for period in next_72h:
        prob = period.get("probabilityOfPrecipitation") or {}
        val = prob.get("value") if isinstance(prob, dict) else None
        if val is not None:
            try:
                pct = int(val)
                if pct > peak_pct:
                    peak_pct = pct
                    peak_period_name = period.get("name")
            except (ValueError, TypeError):
                pass

    return {
        "rain_forecast_pct": peak_pct if peak_pct > 0 else None,
        "rain_forecast_period": peak_period_name if peak_pct > 0 else None,
    }


async def _fetch_observations(client: httpx.AsyncClient, max_pages: int = 3) -> list[dict]:
    """
    KEWN (an augmented ASOS) reports roughly every 5 minutes, not hourly, and
    this endpoint caps at 500 observations per page — one page only reaches
    back about 40 hours. A single-page fetch (the previous `limit=73` reached
    back barely 6-8 hours) silently truncated the "72h" rainfall window to
    whatever the last few hours happened to be, which is how confirmed
    same-day rain could still show 0.00in. Page through pagination.next until
    72h of coverage is reached (typically 2 pages).
    """
    all_features: list[dict] = []
    url = f"{NOAA_BASE}/stations/{NOAA_STATION}/observations"
    params: dict | None = {"limit": 500}
    now = datetime.now(timezone.utc)

    for _ in range(max_pages):
        resp = await client.get(url, params=params, headers=NOAA_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        all_features.extend(features)

        timestamps = [
            f["properties"]["timestamp"]
            for f in features
            if f.get("properties", {}).get("timestamp")
        ]
        if not timestamps:
            break
        oldest = min(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in timestamps)
        if (now - oldest).total_seconds() / 3600 >= 73:
            break

        next_url = data.get("pagination", {}).get("next")
        if not next_url:
            break
        url, params = next_url, None

    return all_features


async def _fetch_rain_and_wind() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            features = await _fetch_observations(client)
    except Exception as e:
        logger.warning("NOAA weather API failed: %s", e)
        return {"error": str(e), "rain_24h_in": None, "rain_72h_in": None,
                "wind_speed_mph": None, "wind_direction": None}

    now = datetime.now(timezone.utc)

    # precipitationLastHour is the METAR "P" group: rain since the last
    # routine hourly report (KEWN's go out at :54), reset right after it. The
    # 5-minute and special observations in between carry the running total,
    # so within one routine-to-routine period the readings only climb and the
    # period's total is its largest reading. Summing every reading counts the
    # same rain many times over; chaining back-to-back periods into a single
    # "burst" keeps just one hour of a multi-hour storm. Summing per-period
    # maxima matched KEWN's own 24h total group exactly (70132 = 1.32" for
    # 12Z Oct 3–4, 2026), where the burst method gave about a third of it.
    readings: list[tuple[datetime, float]] = []
    wind_speed_mph = None
    wind_direction = None
    latest_set = False

    for feature in features:
        props = feature.get("properties", {})
        ts_str = props.get("timestamp")
        if not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue

        precip = props.get("precipitationLastHour", {})
        precip_val = precip.get("value") if isinstance(precip, dict) else None
        if precip_val is not None:
            try:
                v = float(precip_val)
                if not math.isnan(v) and v >= 0:
                    readings.append((ts, v))
            except (ValueError, TypeError):
                pass

        if not latest_set:
            wind = props.get("windSpeed", {})
            wind_val = wind.get("value") if isinstance(wind, dict) else None
            if wind_val is not None:
                try:
                    # NOAA gives wind speed in km/h in the geo+json format
                    wind_speed_mph = float(wind_val) * 0.621371
                except (ValueError, TypeError):
                    pass

            wind_dir_prop = props.get("windDirection", {})
            wind_dir_val = wind_dir_prop.get("value") if isinstance(wind_dir_prop, dict) else None
            if wind_dir_val is not None:
                try:
                    wind_direction = _deg_to_cardinal(float(wind_dir_val))
                except (ValueError, TypeError):
                    pass

            if wind_speed_mph is not None:
                latest_set = True

    # Shift timestamps so a routine report lands in the same clock hour as the
    # readings leading up to it, and anything after it in the next hour.
    shift = timedelta(minutes=59 - _ROUTINE_REPORT_MINUTE)
    periods: dict[datetime, tuple[datetime, float]] = {}
    for ts, v in readings:
        key = (ts + shift).replace(minute=0, second=0, microsecond=0)
        last_ts, peak = periods.get(key, (ts, v))
        periods[key] = (max(last_ts, ts), max(peak, v))

    rain_24h_mm = 0.0
    rain_72h_mm = 0.0
    for last_ts, peak_val in periods.values():
        age_hours = (now - last_ts).total_seconds() / 3600
        if age_hours <= 24:
            rain_24h_mm += peak_val
        if age_hours <= 72:
            rain_72h_mm += peak_val

    return {
        "rain_24h_in": round(_mm_to_in(rain_24h_mm), 2),
        "rain_72h_in": round(_mm_to_in(rain_72h_mm), 2),
        "wind_speed_mph": round(wind_speed_mph, 1) if wind_speed_mph is not None else None,
        "wind_direction": wind_direction,
    }
