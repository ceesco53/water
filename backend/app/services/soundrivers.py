import logging
import re
import time
from datetime import date, datetime, timezone

import httpx

logger = logging.getLogger(__name__)

SOUNDRIVERS_URL = "https://soundrivers.org/swim-guide/"

# Sound Rivers publishes free-text weekly results on a WordPress page, not
# through an API — these are the exact site names (as of 2026) covering the
# Trent River corridor around River Bend, matched case-insensitively against
# the flattened page text. If Sound Rivers ever renames a site or restructures
# the page, matches quietly drop out and the dashboard leans on NC DEQ's
# samples alone rather than crashing or reporting stale/wrong data.
TARGET_SITES = [
    "River Bend",
    "Trent Woods",
    "Brices Creek",
    "Lawson Creek Park",
    "Spring Garden",
    "Glenburnie",
    "Pollocksville",
]

# Every status word observed on the page as of 2026-08; anything else found
# maps to "unknown" rather than being guessed at.
_STATUS_MAP = {
    "pass": "safe",
    "fail": "unsafe",
    "not tested": "unknown",
}

# A plain httpx UA gets a hard Cloudflare block here; a browser-shaped one
# doesn't. Even so, this has been observed to intermittently 403 the exact
# same request within the same session — treat failures as routine, not
# exceptional.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Sound Rivers updates this page weekly; polling it every 30 minutes (this
# app's normal refresh cadence) would just hammer a small nonprofit's site for
# no benefit and risks tripping Cloudflare into a harder, longer-lived block.
# Successes are cached longer than failures so a transient block clears
# within an hour instead of sitting for the full 6.
_SUCCESS_CACHE_SECONDS = 6 * 3600
_FAILURE_CACHE_SECONDS = 3600
_cache: dict = {"data": None, "ts": 0.0}


def _parse_week_of(text: str) -> date | None:
    """
    Sound Rivers writes the date by hand, in whatever style that week's
    author prefers — "September 4, 2026", "Sept. 4, 2026", "Aug 28, 2026".
    Strip periods, fold "Sept" to strptime's "Sep", then try both the
    abbreviated and full month-name formats.
    """
    cleaned = re.sub(r"\bSept\b", "Sep", text.replace(".", ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    logger.warning("Sound Rivers page: unparseable week-of date %r", text)
    return None


def _extract_week_of(html: str) -> str | None:
    m = re.search(
        r"Conditions for the week of.*?<strong>([^<]+)</strong>",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _flatten(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&#8211;", "-")
        .replace("&#8212;", "-")
        .replace("&#8217;", "'")
        .replace("&amp;", "&")
    )
    return re.sub(r"\s+", " ", text)


async def _fetch_and_parse() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
            resp = await client.get(SOUNDRIVERS_URL)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning("Sound Rivers page fetch failed: %s", e)
        return []

    text = _flatten(html)
    week_of = _extract_week_of(html)
    sample_date = _parse_week_of(week_of) if week_of else None
    age_days = (datetime.now(timezone.utc).date() - sample_date).days if sample_date else None

    readings = []
    for name in TARGET_SITES:
        m = re.search(rf"{re.escape(name)}\s*[-–—]\s*(pass|fail|not tested)", text, re.IGNORECASE)
        if not m:
            continue
        readings.append({
            "source": "Sound Rivers",
            "site_id": name.lower().replace(" ", "-"),
            "site_name": name,
            "status": _STATUS_MAP.get(m.group(1).lower(), "unknown"),
            "advisory": None,
            "sample_date": sample_date.isoformat() if sample_date else None,
            "age_days": age_days,
            "mpn": None,
            "geomean_mpn": None,
            "salinity_ppt": None,
            "water_temp_f": None,
            "source_url": SOUNDRIVERS_URL,
        })

    if not readings:
        logger.warning("Sound Rivers page: no known Trent-corridor sites matched — page format may have changed")
    return readings


async def fetch_soundrivers_page() -> list[dict]:
    """
    Weekly pass/fail results for River Bend and nearby Trent River sites,
    scraped from Sound Rivers' own swim guide page — the same data a person
    checking soundrivers.org by hand would see: no numeric bacteria value,
    just pass/fail/not-tested per site, River Bend first. Sampling runs
    Memorial Day through Labor Day only; the page keeps showing the last
    week's results all off-season, so callers must weigh age_days.
    """
    now = time.time()
    cached = _cache["data"]
    if cached is not None:
        ttl = _SUCCESS_CACHE_SECONDS if cached else _FAILURE_CACHE_SECONDS
        if now - _cache["ts"] < ttl:
            return cached

    result = await _fetch_and_parse()
    _cache["data"] = result
    _cache["ts"] = now
    return result
