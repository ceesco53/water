import logging
import re
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

SOUNDRIVERS_URL = "https://soundrivers.org/swim-guide/"

# Sound Rivers publishes free-text weekly results on a WordPress page, not
# through an API — these are the exact site names (as of 2026) covering the
# Trent River corridor around River Bend, matched case-insensitively against
# the flattened page text. If Sound Rivers ever renames a site or restructures
# the page, matches quietly drop out and the caller falls through to the next
# source in the chain rather than crashing or reporting stale/wrong data.
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

_STATUS_RANK = {"unsafe": 3, "caution": 2, "safe": 1, "unknown": 0}

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


async def _fetch_and_parse() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
            resp = await client.get(SOUNDRIVERS_URL)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning("Sound Rivers page fetch failed: %s", e)
        return {"status": "unknown", "beaches": [], "source": "Sound Rivers", "source_url": SOUNDRIVERS_URL}

    text = _flatten(html)
    week_of = _extract_week_of(html)

    age_days = None
    if week_of:
        try:
            sample_date = datetime.strptime(week_of, "%B %d, %Y").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - sample_date).days
        except ValueError:
            pass

    beaches = []
    worst_status = "unknown"
    for name in TARGET_SITES:
        m = re.search(rf"{re.escape(name)}\s*[-–—]\s*(pass|fail|not tested)", text, re.IGNORECASE)
        if not m:
            continue
        status = _STATUS_MAP.get(m.group(1).lower(), "unknown")
        beaches.append({
            "id": name.lower().replace(" ", "-"),
            "name": name,
            "status": status,
            "status_code": None,
        })
        if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(worst_status, 0):
            worst_status = status

    if not beaches:
        logger.warning("Sound Rivers page: no known Trent-corridor sites matched — page format may have changed")
        return {"status": "unknown", "beaches": [], "source": "Sound Rivers", "source_url": SOUNDRIVERS_URL}

    return {
        "status": worst_status,
        "beaches": beaches,
        "source": "Sound Rivers",
        "source_url": SOUNDRIVERS_URL,
        "latest_mpn": None,
        "latest_date": week_of,
        "age_days": age_days,
    }


async def fetch_soundrivers_page() -> dict:
    """
    Weekly pass/fail results for River Bend and nearby Trent River sites,
    scraped from Sound Rivers' own swim guide page. This is the same data a
    person checking soundrivers.org by hand would see — no numeric bacteria
    value, just pass/fail/not-tested per site — used as a middle tier between
    the (partner-key-gated) Swim Guide API and the EPA WQP fallback, which
    only covers Neuse River sites several miles from River Bend.
    """
    now = time.time()
    cached = _cache["data"]
    if cached is not None:
        ttl = _SUCCESS_CACHE_SECONDS if cached.get("status") != "unknown" else _FAILURE_CACHE_SECONDS
        if now - _cache["ts"] < ttl:
            return cached

    result = await _fetch_and_parse()
    _cache["data"] = result
    _cache["ts"] = now
    return result
