import math

# River Bend town hall — the point the NWS forecast grid cell (MHX/41,72) was
# resolved from, and the center of every "near River Bend" radius query.
RIVER_BEND_LAT = 35.0728
RIVER_BEND_LON = -77.1485

_EARTH_RADIUS_MI = 3958.8


def miles_from_river_bend(lat: float, lon: float) -> float:
    """Great-circle (haversine) distance from River Bend, in statute miles."""
    p1, p2 = math.radians(RIVER_BEND_LAT), math.radians(lat)
    dp = p2 - p1
    dl = math.radians(lon - RIVER_BEND_LON)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_MI * math.asin(math.sqrt(a))
