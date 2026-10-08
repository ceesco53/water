import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import history, risk_model
from .scoring import (
    BACTERIA_FULL_WEIGHT_DAYS,
    compute_score,
    select_bacteria_reading,
    vibrio_risk,
)
from .services.ncdeq_events import LOOKBACK_DAYS, RADIUS_MI, fetch_sewer_spills, fetch_water_incidents
from .services.ncdeq_rwq import fetch_ncdeq_rwq
from .services.radar_rain import fetch_radar_rain
from .services.soundrivers import fetch_soundrivers_page
from .services.usgs import fetch_usgs_data
from .services.weather import fetch_weather_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "1800"))
_cache: dict = {}

# DEQ measures salinity at each bacteria sample; it shifts with river flow,
# so an older reading is still a fair guide for the Vibrio indicator.
_SALINITY_MAX_AGE_DAYS = 21



async def _refresh() -> dict:
    """Rebuild conditions, cache them, and log them to the history DB."""
    data = await _build_conditions()
    _cache["data"] = data
    _cache["ts"] = time.time()
    await asyncio.to_thread(history.record, data)
    return data


async def _refresh_loop() -> None:
    # Refresh on a timer, not only when someone loads the page, so the
    # history log has an unbroken record to grade the model against.
    while True:
        try:
            await _refresh()
        except Exception as e:
            logger.error("Scheduled refresh failed: %s", e)
        await asyncio.sleep(CACHE_TTL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="River Bend Water Monitor", version="1.0.0", lifespan=lifespan)


def _or_default(result, name: str, default):
    if isinstance(result, Exception):
        logger.error("%s fetch failed: %s", name, result)
        return default
    return result


def _freshest(readings: list[dict], field: str, max_age_days: int):
    """Newest DEQ reading carrying `field`, if one is recent enough."""
    candidates = [
        r for r in readings
        if r.get(field) is not None and r["age_days"] <= max_age_days
    ]
    return min(candidates, key=lambda r: r["age_days"]) if candidates else None


async def _build_conditions() -> dict:
    usgs_res, weather_res, radar_res, sr_res, deq_res, incidents, spills = await asyncio.gather(
        fetch_usgs_data(),
        fetch_weather_data(),
        fetch_radar_rain(),
        fetch_soundrivers_page(),
        fetch_ncdeq_rwq(),
        fetch_water_incidents(),
        fetch_sewer_spills(),
        return_exceptions=True,
    )
    usgs_res = _or_default(usgs_res, "USGS", {})
    weather_res = _or_default(weather_res, "Weather", {})
    radar_res = _or_default(radar_res, "Radar rain", {})
    sr_res = _or_default(sr_res, "Sound Rivers", [])
    deq_res = _or_default(deq_res, "NC DEQ swim sampling", [])
    incidents = _or_default(incidents, "NC DEQ fish kills", None)
    spills = _or_default(spills, "NC DEQ sewer spills", None)

    # Sound Rivers samples River Bend itself, weekly, Memorial Day–Labor Day.
    # NC DEQ samples Union Point at the mouth of the Trent year-round. The
    # freshest result from the most relevant water wins (see
    # select_bacteria_reading) rather than a fixed source order.
    readings = sr_res + deq_res
    primary = select_bacteria_reading(readings)

    # DEQ measures water temperature on site when it samples, which beats
    # the Beaufort ocean-inlet proxy whenever that sample is recent.
    temp_reading = _freshest(deq_res, "water_temp_f", BACTERIA_FULL_WEIGHT_DAYS)
    if temp_reading:
        water_temp_f = temp_reading["water_temp_f"]
        water_temp_source = f"NC DEQ sample at {temp_reading['site_name'].split(',')[0]}"
        water_temp_date = temp_reading["sample_date"]
    else:
        water_temp_f = weather_res.get("water_temp_f")
        water_temp_source = weather_res.get("water_temp_source")
        water_temp_date = None

    # Salinity is site-specific -- the Neuse runs far saltier than River
    # Bend's stretch of the Trent -- so only Trent-side samples count.
    # (Water temperature is regional; the freshest sample anywhere will do.)
    trent_deq = [r for r in deq_res if r.get("reach") != "neuse"]
    salinity_reading = _freshest(trent_deq, "salinity_ppt", _SALINITY_MAX_AGE_DAYS)
    salinity_ppt = salinity_reading["salinity_ppt"] if salinity_reading else None

    upstream = usgs_res.get("02092500", {})
    local = usgs_res.get("02092554", {})

    rain_24h = weather_res.get("rain_24h_in")
    rain_72h = weather_res.get("rain_72h_in")
    rain_7d = weather_res.get("rain_7d_in")
    rain_gauge_issue = weather_res.get("rain_gauge_issue")
    alerts = weather_res.get("alerts")

    radar_72h = radar_res.get("radar_rain_72h_in")
    radar_7d = radar_res.get("radar_rain_7d_in")

    # Chance a sample today would exceed the swim standard. The model was
    # trained on KEWN's gauge, so that's its rain input -- unless the gauge
    # is out or missing reports, when radar at HOME stands in rather than
    # the zeros KEWN reports; with neither, rain is held at its average.
    flow_cfs, flow_p80 = upstream.get("discharge_cfs"), upstream.get("discharge_cfs_p80")
    if rain_gauge_issue is None and rain_72h is not None:
        model_72h, model_7d, rain_source = rain_72h, rain_7d, "KEWN"
    elif radar_72h is not None:
        model_72h, model_7d, rain_source = radar_72h, radar_7d, "radar"
    else:
        model_72h, model_7d, rain_source = None, None, None
    try:
        bacteria_risk = risk_model.predict(
            rain_72h_in=model_72h,
            rain_7d_in=model_7d,
            flow_ratio=flow_cfs / flow_p80 if flow_cfs is not None and flow_p80 else None,
            day=datetime.now(timezone.utc).date(),
            storm_rain_72h_in=radar_72h,
        )
        bacteria_risk["rain_source"] = rain_source
    except Exception as e:
        logger.error("Bacteria risk model failed: %s", e)
        bacteria_risk = None

    score, rating, color, factors = compute_score(
        bacteria=primary,
        bacteria_risk=bacteria_risk,
        nws_alerts=alerts,
        thunder_pct_6h=weather_res.get("thunder_pct_6h"),
        incidents=incidents,
        sewer_spills=spills,
    )

    return {
        "score": score,
        "rating": rating,
        "rating_color": color,
        "score_factors": factors,
        "bacteria": {
            "primary": primary,
            "readings": readings,
        },
        "bacteria_risk": bacteria_risk,
        "weather": {
            "rain_24h_in": rain_24h,
            "rain_72h_in": rain_72h,
            "rain_7d_in": rain_7d,
            "rain_gauge_issue": rain_gauge_issue,
            "radar_rain_24h_in": radar_res.get("radar_rain_24h_in"),
            "radar_rain_72h_in": radar_72h,
            "radar_rain_7d_in": radar_7d,
            "radar_through": radar_res.get("radar_through"),
            "wind_speed_mph": weather_res.get("wind_speed_mph"),
            "wind_direction": weather_res.get("wind_direction"),
            "rain_forecast_pct": weather_res.get("rain_forecast_pct"),
            "rain_forecast_period": weather_res.get("rain_forecast_period"),
            "qpf_72h_in": weather_res.get("qpf_72h_in"),
            "thunder_pct_6h": weather_res.get("thunder_pct_6h"),
            "thunder_pct_24h": weather_res.get("thunder_pct_24h"),
        },
        "alerts": alerts,
        "reports": {
            "radius_mi": RADIUS_MI,
            "lookback_days": LOOKBACK_DAYS,
            "incidents": incidents,
            "sewer_spills": spills,
        },
        "water": {
            "temp_f": water_temp_f,
            "temp_source": water_temp_source,
            "temp_date": water_temp_date,
            "salinity_ppt": salinity_ppt,
            "salinity_site": salinity_reading["site_name"] if salinity_reading else None,
            "salinity_date": salinity_reading["sample_date"] if salinity_reading else None,
        },
        "vibrio": vibrio_risk(water_temp_f, salinity_ppt),
        "gauges": {
            "upstream": {
                "site_code": "02092500",
                "site_name": "Trent River near Trenton",
                "description": "~17 mi upstream — runoff indicator; discharge feeds the score",
                "discharge_cfs": upstream.get("discharge_cfs"),
                "gage_height_ft": upstream.get("gage_height_ft"),
                "discharge_p80": upstream.get("discharge_cfs_p80"),
            },
            "local": {
                "site_code": "02092554",
                "site_name": "Trent River at Pollocksville",
                "description": "Closest active gauge to River Bend (~6 mi upstream) — stage only, no discharge sensor",
                "discharge_cfs": local.get("discharge_cfs"),
                "gage_height_ft": local.get("gage_height_ft"),
            },
        },
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/conditions")
async def get_conditions():
    now = time.time()
    if _cache.get("data") and now - _cache.get("ts", 0) < CACHE_TTL:
        data = dict(_cache["data"])
        data["cache_age_seconds"] = int(now - _cache["ts"])
        return data

    data = await _refresh()
    data["cache_age_seconds"] = 0
    return data


@app.post("/api/refresh")
async def force_refresh():
    _cache.clear()
    data = await _refresh()
    data["cache_age_seconds"] = 0
    return data


@app.get("/api/history/{table}")
async def get_history(table: str, since: str | None = None):
    """Logged snapshots or samples (see history.py), e.g. ?since=2027-05-01."""
    if table not in ("snapshots", "samples"):
        raise HTTPException(status_code=404, detail="Unknown history table")
    return await asyncio.to_thread(history.export, table, since)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve React SPA — must be registered after API routes
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(_static_dir, "index.html"))
