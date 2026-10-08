"""
Running log of what the dashboard saw and predicted, so the bacteria-risk
model -- trained on Union Point and NW Creek -- can be graded against River
Bend's own samples as they come in (step 6 of the calibration workflow).

  snapshots  one row per refresh (every CACHE_TTL_SECONDS): score, the
             model's probability and inputs, both rain sources, river flow,
             and which bacteria result drove the score
  samples    one row per bacteria result, recorded the first time it's seen
             -- so every weekly River Bend pass/fail is kept even after
             Sound Rivers' page moves on to the next week

SQLite at HISTORY_DB (k8s: the water-history persistent volume). If that
location isn't writable -- local dev, say -- logging is skipped with a single
warning and the dashboard runs as before.
"""
import json
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("HISTORY_DB", "/data/water-history.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    ts TEXT PRIMARY KEY,
    score INTEGER,
    rating TEXT,
    risk_probability REAL,
    risk_caution_line REAL,
    summer_storm INTEGER,
    model_rain_source TEXT,
    kewn_rain_24h REAL,
    kewn_rain_72h REAL,
    kewn_rain_7d REAL,
    rain_gauge_issue TEXT,
    radar_rain_24h REAL,
    radar_rain_72h REAL,
    radar_rain_7d REAL,
    flow_cfs REAL,
    flow_p80 REAL,
    bacteria_source TEXT,
    bacteria_site TEXT,
    bacteria_status TEXT,
    bacteria_age_days INTEGER,
    factors TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    source TEXT,
    site_id TEXT,
    sample_date TEXT,
    site_name TEXT,
    reach TEXT,
    status TEXT,
    mpn REAL,
    geomean_mpn REAL,
    advisory TEXT,
    salinity_ppt REAL,
    water_temp_f REAL,
    first_seen TEXT,
    PRIMARY KEY (source, site_id, sample_date)
);
"""

_disabled = False


def _connect() -> sqlite3.Connection | None:
    global _disabled
    if _disabled:
        return None
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.row_factory = sqlite3.Row
        return conn
    except (OSError, sqlite3.Error) as e:
        _disabled = True
        logger.warning("History logging disabled -- can't open %s: %s", DB_PATH, e)
        return None


def record(conditions: dict) -> None:
    """Log one refresh. Blocking; call it via asyncio.to_thread."""
    conn = _connect()
    if conn is None:
        return
    risk = conditions.get("bacteria_risk") or {}
    weather = conditions.get("weather") or {}
    upstream = (conditions.get("gauges") or {}).get("upstream") or {}
    primary = (conditions.get("bacteria") or {}).get("primary") or {}
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO snapshots VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    conditions["last_updated"],
                    conditions.get("score"),
                    conditions.get("rating"),
                    risk.get("probability"),
                    risk.get("caution_probability"),
                    int(bool(risk.get("summer_storm"))) if risk else None,
                    risk.get("rain_source"),
                    weather.get("rain_24h_in"),
                    weather.get("rain_72h_in"),
                    weather.get("rain_7d_in"),
                    weather.get("rain_gauge_issue"),
                    weather.get("radar_rain_24h_in"),
                    weather.get("radar_rain_72h_in"),
                    weather.get("radar_rain_7d_in"),
                    upstream.get("discharge_cfs"),
                    upstream.get("discharge_p80"),
                    primary.get("source"),
                    primary.get("site_id"),
                    primary.get("status"),
                    primary.get("age_days"),
                    json.dumps(conditions.get("score_factors") or []),
                ),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        r.get("source"), r.get("site_id"), r.get("sample_date"),
                        r.get("site_name"), r.get("reach"), r.get("status"),
                        r.get("mpn"), r.get("geomean_mpn"), r.get("advisory"),
                        r.get("salinity_ppt"), r.get("water_temp_f"),
                        conditions["last_updated"],
                    )
                    for r in (conditions.get("bacteria") or {}).get("readings", [])
                    if r.get("sample_date")
                ],
            )
    except sqlite3.Error as e:
        logger.warning("History write failed: %s", e)
    finally:
        conn.close()


def export(table: str, since: str | None = None) -> list[dict]:
    """Rows from `snapshots` (by ts) or `samples` (by sample_date), oldest first."""
    if table not in ("snapshots", "samples"):
        raise ValueError(table)
    conn = _connect()
    if conn is None:
        return []
    key = "ts" if table == "snapshots" else "sample_date"
    try:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE ? IS NULL OR {key} >= ? ORDER BY {key}",
            (since, since),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
