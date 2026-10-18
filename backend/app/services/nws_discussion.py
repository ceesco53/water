import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from .weather import NOAA_BASE, NOAA_HEADERS, NWS_GRID

logger = logging.getLogger(__name__)

# River Bend's NWS forecast office (Newport/Morehead City), from its grid cell
OFFICE = NWS_GRID.split("/")[0]
DISCUSSION_URL = f"https://forecast.weather.gov/product.php?site={OFFICE}&issuedby={OFFICE}&product=AFD"

# A discussion older than this no longer describes what's happening now
_MAX_AGE = timedelta(hours=24)
_MAX_EXCERPTS = 3
_MAX_CHARS = 360

# Sections written specifically about water, quoted whole when present...
_WATER_SECTIONS = ("TIDES/COASTAL FLOODING", "COASTAL FLOODING", "HYDROLOGY")
# ...otherwise the summary sections, keeping only paragraphs about what
# moves water: weather systems, wind, tides, surge, rain and flooding.
_SUMMARY_SECTIONS = ("KEY MESSAGES", "SYNOPSIS")
_WATER_WORDS = re.compile(
    r"(?i)nor'?easter|low pressure|coastal low|tropical|hurricane|storm|surge|coastal flood|"
    r"water level|tide|tidal|soundside|wind|rain|flood"
)
# Paragraphs that only list zones or products, e.g. "Coastal Flood Advisory until ... for NCZ046"
_ZONE_LIST = re.compile(r"\bNCZ\d{3}")


def _sections(text: str) -> dict[str, str]:
    """AFD sections, keyed by name: '.KEY MESSAGES...' through the next '.NAME...' or '&&'."""
    out = {}
    for m in re.finditer(r"^\.([A-Z][A-Z/ ]+?)\.\.\.(.*?)(?=^\.[A-Z][A-Z/ ]+?\.\.\.|^&&|\Z)", text, re.S | re.M):
        out.setdefault(m.group(1).strip(), m.group(2))
    return out


def _paragraphs(section: str) -> list[str]:
    paras = []
    for block in re.split(r"\n\s*\n", section):
        p = " ".join(block.split())
        p = re.sub(r"^\d\)\s*", "", p)  # numbered key messages: "1) ..."
        if p and not _ZONE_LIST.search(p):
            paras.append(p)
    return paras


def _trim(p: str) -> str:
    """Cut at a sentence end under _MAX_CHARS, so quotes stay verbatim, just shorter."""
    if len(p) <= _MAX_CHARS:
        return p
    cut = p[:_MAX_CHARS]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > 80 else cut.rsplit(" ", 1)[0]) + " …"


def excerpts(text: str) -> list[str]:
    """The passages of an AFD that explain what's moving the water, verbatim."""
    sections = _sections(text)
    picked: list[str] = []
    for name in _WATER_SECTIONS:
        picked += _paragraphs(sections.get(name, ""))
    if not picked:
        for name in _SUMMARY_SECTIONS:
            picked += [p for p in _paragraphs(sections.get(name, "")) if _WATER_WORDS.search(p)]
    seen, out = set(), []
    for p in picked:
        if p not in seen:
            seen.add(p)
            out.append(_trim(p))
    return out[:_MAX_EXCERPTS]


async def fetch_forecast_discussion() -> dict | None:
    """
    The latest Area Forecast Discussion from River Bend's NWS office -- the
    forecasters' own explanation of what's driving the weather -- reduced to
    its passages about water. None if unreachable, stale, or silent on water.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            listing = await client.get(f"{NOAA_BASE}/products/types/AFD/locations/{OFFICE}", headers=NOAA_HEADERS)
            listing.raise_for_status()
            latest = (listing.json().get("@graph") or [None])[0]
            if latest is None:
                return None
            resp = await client.get(f"{NOAA_BASE}/products/{latest['id']}", headers=NOAA_HEADERS)
            resp.raise_for_status()
            product = resp.json()
    except Exception as e:
        logger.warning("NWS forecast discussion fetch failed: %s", e)
        return None

    issued = datetime.fromisoformat(product["issuanceTime"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - issued > _MAX_AGE:
        return None
    text = product.get("productText") or ""
    found = excerpts(text)
    if not found:
        return None
    office = re.search(r"National Weather Service (.+)", text)
    return {
        "office": f"NWS {office.group(1).strip()}" if office else f"NWS {OFFICE}",
        "issued": issued.isoformat(),
        "excerpts": found,
        "url": DISCUSSION_URL,
    }
