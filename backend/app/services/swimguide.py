import httpx
import logging

logger = logging.getLogger(__name__)

SWIMGUIDE_BASE = "https://www.theswimguide.org/api/v2"

TARGET_KEYWORDS = ["river bend", "trent", "brices creek", "lawson", "new bern", "trent woods"]

# Swim Guide status codes: 1=safe, 2=unsafe, 3=caution, 4=no_data
STATUS_MAP = {1: "safe", 2: "unsafe", 3: "caution", 4: "unknown"}


async def fetch_swimguide_data() -> dict:
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                f"{SWIMGUIDE_BASE}/beaches/",
                params={"search": "New Bern", "country": "US"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            raw = resp.json()
    except Exception as e:
        logger.warning(f"Swim Guide API unavailable: {e}")
        return {"status": "unknown", "beaches": [], "error": str(e)}

    beaches_list = raw if isinstance(raw, list) else raw.get("results", raw.get("beaches", []))

    relevant = []
    for beach in beaches_list:
        name = beach.get("name", "").lower()
        if any(kw in name for kw in TARGET_KEYWORDS):
            status_code = beach.get("status") or beach.get("safetyStatus")
            relevant.append(
                {
                    "id": beach.get("id"),
                    "name": beach.get("name"),
                    "status": STATUS_MAP.get(status_code, "unknown"),
                    "status_code": status_code,
                }
            )

    # Fallback: take first few results if none matched keywords
    if not relevant and beaches_list:
        for beach in beaches_list[:5]:
            status_code = beach.get("status") or beach.get("safetyStatus")
            relevant.append(
                {
                    "id": beach.get("id"),
                    "name": beach.get("name"),
                    "status": STATUS_MAP.get(status_code, "unknown"),
                    "status_code": status_code,
                }
            )

    status_codes = [b.get("status_code") for b in relevant if b.get("status_code") is not None]

    if not status_codes:
        agg = "unknown"
    elif any(s == 2 for s in status_codes):
        agg = "unsafe"
    elif any(s == 3 for s in status_codes):
        agg = "caution"
    elif all(s == 1 for s in status_codes):
        agg = "safe"
    else:
        agg = "unknown"

    return {"status": agg, "beaches": relevant}
