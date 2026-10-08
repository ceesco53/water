import math
import os

# The spot the report is for: the center of every "nearby" radius query,
# distance, NWS alert lookup and radar rainfall reading. Defaults to River
# Bend's town hall; set HOME_LAT / HOME_LON to a specific address. In k8s they
# come from the optional `water-home` ConfigMap, kept out of this (public)
# repo. Anywhere in River Bend shares NWS forecast grid cell MHX/41,72.
HOME_LAT = float(os.getenv("HOME_LAT", "35.0728"))
HOME_LON = float(os.getenv("HOME_LON", "-77.1485"))

_EARTH_RADIUS_MI = 3958.8


def miles_from_home(lat: float, lon: float) -> float:
    """Great-circle (haversine) distance from HOME, in statute miles."""
    p1, p2 = math.radians(HOME_LAT), math.radians(lat)
    dp = p2 - p1
    dl = math.radians(lon - HOME_LON)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_MI * math.asin(math.sqrt(a))
