import httpx
import math
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

NOAA_BASE = "https://api.weather.gov"
# Craven County Regional Airport (KEWN) — closest ASOS station to New Bern
NOAA_STATION = "KEWN"
NOAA_HEADERS = {
    "User-Agent": "(water-monitor/1.0, ceesco53@gmail.com)",
    "Accept": "application/geo+json",
}

# NOAA CO-OPS: Beaufort Duke Marine Lab (~40mi SE of New Bern)
# Closest station with real-time water temperature on the inner coast.
# No USGS sensor exists on any Trent River gauge (00010 unavailable at all 3 sites).
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
    rain_wind = await _fetch_rain_and_wind()
    water_temp = await fetch_water_temp_f()
    return {**rain_wind, **water_temp}


async def _fetch_rain_and_wind() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{NOAA_BASE}/stations/{NOAA_STATION}/observations",
                params={"limit": 73},
                headers=NOAA_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("NOAA weather API failed: %s", e)
        return {"error": str(e), "rain_24h_in": None, "rain_72h_in": None,
                "wind_speed_mph": None, "wind_direction": None}

    features = data.get("features", [])
    now = datetime.now(timezone.utc)

    rain_24h_mm = 0.0
    rain_72h_mm = 0.0
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
            age_hours = (now - ts).total_seconds() / 3600
        except Exception:
            continue

        precip = props.get("precipitationLastHour", {})
        precip_val = precip.get("value") if isinstance(precip, dict) else None
        if precip_val is not None:
            try:
                v = float(precip_val)
                if not math.isnan(v) and v >= 0:
                    if age_hours <= 24:
                        rain_24h_mm += v
                    if age_hours <= 72:
                        rain_72h_mm += v
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

    return {
        "rain_24h_in": round(_mm_to_in(rain_24h_mm), 2),
        "rain_72h_in": round(_mm_to_in(rain_72h_mm), 2),
        "wind_speed_mph": round(wind_speed_mph, 1) if wind_speed_mph is not None else None,
        "wind_direction": wind_direction,
    }
