import httpx
import logging

logger = logging.getLogger(__name__)

USGS_BASE = "https://waterservices.usgs.gov/nwis/iv/"

STATIONS = {
    "02092500": "Trent River near Trenton (upstream)",
    "02092576": "Trent River at Hwy 70, New Bern (local)",
    # 02092558 omitted — station inactive since 1961, water-quality samples only, no real-time data
}

PARAM_NAMES = {
    "00060": "discharge_cfs",
    "00065": "gage_height_ft",
    "00010": "water_temp_c",
}


async def fetch_usgs_data() -> dict:
    params = {
        "format": "json",
        "sites": ",".join(STATIONS.keys()),
        "parameterCd": "00060,00065,00010",
        "period": "P7D",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(USGS_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"USGS API failed: {e}")
        return {}

    result: dict = {}

    for ts in data.get("value", {}).get("timeSeries", []):
        site_code = ts["sourceInfo"]["siteCode"][0]["value"]
        var_code = ts["variable"]["variableCode"][0]["value"]
        param_name = PARAM_NAMES.get(var_code, var_code)

        values = ts.get("values", [{}])[0].get("value", [])
        valid_values = [
            float(v["value"])
            for v in values
            if v.get("value") and v["value"] not in ("-999999", "")
        ]

        if site_code not in result:
            result[site_code] = {
                "site_name": STATIONS.get(site_code, site_code),
                "site_code": site_code,
            }

        if valid_values:
            result[site_code][param_name] = valid_values[-1]
            if len(valid_values) > 1:
                sorted_vals = sorted(valid_values)
                p80_idx = int(0.80 * len(sorted_vals))
                result[site_code][f"{param_name}_p80"] = sorted_vals[p80_idx]

    return result
