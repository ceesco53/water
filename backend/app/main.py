import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .scoring import compute_score
from .services.bacteria import fetch_bacteria_wqp
from .services.swimguide import fetch_swimguide_data
from .services.usgs import fetch_usgs_data
from .services.weather import fetch_weather_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "1800"))
_cache: dict = {}

app = FastAPI(title="River Bend Water Monitor", version="1.0.0")


async def _build_conditions() -> dict:
    usgs_res, swimguide_res, weather_res = await asyncio.gather(
        fetch_usgs_data(),
        fetch_swimguide_data(),
        fetch_weather_data(),
        return_exceptions=True,
    )

    if isinstance(usgs_res, Exception):
        logger.error("USGS fetch failed: %s", usgs_res)
        usgs_res = {}
    if isinstance(swimguide_res, Exception):
        logger.error("SwimGuide fetch failed: %s", swimguide_res)
        swimguide_res = {"status": "unknown", "beaches": []}
    if isinstance(weather_res, Exception):
        logger.error("Weather fetch failed: %s", weather_res)
        weather_res = {}

    # When Swim Guide is unavailable, fall back to EPA WQP bacteria data (station C99)
    if swimguide_res.get("status") == "api_unavailable":
        try:
            wqp_res = await fetch_bacteria_wqp()
            if wqp_res.get("status") != "unknown":
                swimguide_res = wqp_res
                logger.info(
                    "Using EPA WQP bacteria data: %s (age %d days)",
                    wqp_res.get("latest_mpn"),
                    wqp_res.get("age_days", 0),
                )
        except Exception as e:
            logger.error("EPA WQP fallback failed: %s", e)

    upstream = usgs_res.get("02092500", {})
    local = usgs_res.get("02092576", {})

    rain_24h = weather_res.get("rain_24h_in")
    rain_72h = weather_res.get("rain_72h_in")

    score, rating, color, factors = compute_score(
        swimguide_status=swimguide_res.get("status", "unknown"),
        rain_24h_in=rain_24h,
        rain_72h_in=rain_72h,
        upstream_discharge_cfs=upstream.get("discharge_cfs"),
        upstream_discharge_p80=upstream.get("discharge_cfs_p80"),
    )

    return {
        "score": score,
        "rating": rating,
        "rating_color": color,
        "score_factors": factors,
        "swimguide": {
            "status": swimguide_res.get("status", "unknown"),
            "beaches": swimguide_res.get("beaches", []),
            "source_url": swimguide_res.get("source_url"),
            "source": swimguide_res.get("source"),
            "error": swimguide_res.get("error"),
            "latest_mpn": swimguide_res.get("latest_mpn"),
            "latest_date": swimguide_res.get("latest_date"),
            "age_days": swimguide_res.get("age_days"),
        },
        "weather": {
            "rain_24h_in": rain_24h,
            "rain_72h_in": rain_72h,
            "wind_speed_mph": weather_res.get("wind_speed_mph"),
            "wind_direction": weather_res.get("wind_direction"),
        },
        "gauges": {
            "upstream": {
                "site_code": "02092500",
                "site_name": "Trent River near Trenton",
                "description": "Upstream freshwater — runoff indicator",
                "discharge_cfs": upstream.get("discharge_cfs"),
                "gage_height_ft": upstream.get("gage_height_ft"),
                "discharge_p80": upstream.get("discharge_cfs_p80"),
            },
            "local": {
                "site_code": "02092576",
                "site_name": "Trent at Hwy 70, New Bern",
                "description": "Closest gauge to River Bend",
                "discharge_cfs": local.get("discharge_cfs"),
                "gage_height_ft": local.get("gage_height_ft"),
            },
        },
        "water_temp_f": weather_res.get("water_temp_f"),
        "water_temp_source": weather_res.get("water_temp_source"),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/conditions")
async def get_conditions():
    now = time.time()
    if _cache.get("data") and now - _cache.get("ts", 0) < CACHE_TTL:
        data = dict(_cache["data"])
        data["cache_age_seconds"] = int(now - _cache["ts"])
        return data

    data = await _build_conditions()
    _cache["data"] = data
    _cache["ts"] = now
    data["cache_age_seconds"] = 0
    return data


@app.post("/api/refresh")
async def force_refresh():
    _cache.clear()
    data = await _build_conditions()
    _cache["data"] = data
    _cache["ts"] = time.time()
    data["cache_age_seconds"] = 0
    return data


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
