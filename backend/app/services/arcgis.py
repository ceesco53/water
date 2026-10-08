from datetime import date, datetime, timezone

import httpx

from ..geo import HOME_LAT, HOME_LON

# NC DEQ's ArcGIS Online organization — swim advisories, fish kills / algal
# blooms, and sewer overflows are all public feature services under it.
NCDEQ_ARCGIS = "https://services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services"


async def query_layer(client: httpx.AsyncClient, service: str, layer: int, **params) -> list[dict]:
    """
    Query one layer of an NC DEQ feature service, returning each feature's
    attributes with its point geometry (when requested) merged in as
    "lat"/"lon". ArcGIS reports a bad query as HTTP 200 with an "error" body,
    so that's checked explicitly instead of trusting the status code.
    """
    resp = await client.get(
        f"{NCDEQ_ARCGIS}/{service}/FeatureServer/{layer}/query",
        params={"f": "json", "outFields": "*", "returnGeometry": "false", **params},
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"{service}/{layer}: {data['error'].get('message')}")

    rows = []
    for feature in data.get("features", []):
        row = dict(feature.get("attributes") or {})
        geom = feature.get("geometry") or {}
        if "x" in geom and "y" in geom:
            row["lon"], row["lat"] = geom["x"], geom["y"]
        rows.append(row)
    return rows


def within_miles_of_home(miles: float) -> dict:
    """Spatial-filter params: features within `miles` of HOME, geometry returned as WGS84 lat/lon."""
    return {
        "geometry": f"{HOME_LON},{HOME_LAT}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "distance": miles,
        "units": "esriSRUnit_StatuteMile",
        "returnGeometry": "true",
        "outSR": 4326,
    }


def since(field: str, start: date) -> str:
    return f"{field} >= DATE '{start.isoformat()}'"


def epoch_ms_to_date(ms) -> date | None:
    """ArcGIS date fields are epoch milliseconds (UTC)."""
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
