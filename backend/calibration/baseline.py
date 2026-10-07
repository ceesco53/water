"""
Step 3 of score calibration: grade today's formula against history.

Replays the dashboard's original rain and flow rules -- frozen in
legacy_formula.py since the bacteria-risk model replaced them -- on every row
of data/samples.csv, scoring each sample morning as the dashboard would have
with no fresh bacteria result, and measures how well that separated samples that exceeded NC's
standard (>=104 MPN) from those that didn't. Then ranks each candidate input
on its own, to show where the signal is before fitting anything (step 4).

Rows whose rainfall couldn't be confirmed against NOAA's daily record
(rain_check != "ok") are left out of the grading -- KEWN's gauge has
reported zeros through real rain (e.g. Aug-Sep 2025), which would grade the
formula on rain it never saw.

Run from backend/ after build_dataset:
    python -m calibration.baseline
Prints the report and writes calibration/reports/baseline.md.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from calibration.legacy_formula import legacy_score

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "samples.csv"
REPORT = HERE / "reports" / "baseline.md"

SEASON_MONTHS = range(5, 10)  # May–Sep
SEASON_DAYS = 153
BOOTSTRAP = 2000

CANDIDATES = {
    "rain_24h": "Rain, 24h before sample",
    "rain_48h": "Rain, 48h before",
    "rain_72h": "Rain, 72h before",
    "rain_7d": "Rain, 7 days before",
    "flow_ratio": "Trenton flow ÷ day-of-year p80",
    "flow_cfs": "Trenton flow (cfs)",
    "prev_mpn": "Previous sample's MPN",
    "prev_salinity": "Previous sample's salinity",
    "prev_water_temp": "Previous sample's water temp",
    "deq_rainfall_in": "Rain noted by DEQ sampler",
}


def _none_if_nan(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def replay(row) -> tuple[int, str, int]:
    """Score and rating the old dashboard would show with no fresh sample, plus the rain+flow penalty."""
    return legacy_score(
        _none_if_nan(row.rain_24h),
        _none_if_nan(row.rain_72h),
        _none_if_nan(row.flow_cfs),
        _none_if_nan(row.flow_p80),
    )


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """ROC AUC via the Mann-Whitney rank statistic (ties count half)."""
    pos = labels.astype(bool)
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return math.nan
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    return (ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def auc_ci(scores: np.ndarray, labels: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    stats = []
    n = len(scores)
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        a = auc(scores[idx], labels[idx])
        if not math.isnan(a):
            stats.append(a)
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def main() -> None:
    rng = np.random.default_rng(0)
    all_rows = pd.read_csv(DATA)
    df = all_rows[all_rows["rain_check"] == "ok"].copy()
    excluded = len(all_rows) - len(df)

    replayed = df.apply(replay, axis=1, result_type="expand")
    df["score"], df["rating"], df["penalty"] = replayed[0], replayed[1], replayed[2]
    y = df["exceeds"].to_numpy(dtype=bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    in_season = df["month"].isin(SEASON_MONTHS).to_numpy()

    out: list[str] = []
    out.append("# Baseline: how well does today's formula predict bacteria exceedances?\n")
    out.append(
        f"Graded on **{len(df)} NC DEQ samples** ({df['year'].min()}–{df['year'].max()}, Union Point "
        f"and NW Creek) with rainfall confirmed against NOAA's daily record; {excluded} more were "
        f"left out because KEWN's hourly rain disagreed with it or couldn't be checked. "
        f"**{n_pos} exceeded** NC's single-sample standard (≥104 MPN) — {n_pos / len(df):.1%}.\n"
    )
    out.append(
        "Each sample morning is scored the way the original dashboard did when it had no fresh "
        "bacteria result: its 24h/72h rain and upstream-flow rules (max penalty −45, frozen in "
        "`legacy_formula.py`), plus the −5 for missing bacteria data.\n"
    )

    # 1. Overall discrimination
    pen_auc = auc(-df["penalty"].to_numpy(), y)
    lo, hi = auc_ci(-df["penalty"].to_numpy(), y, rng)
    out.append("## 1. Overall\n")
    out.append(
        f"**AUC {pen_auc:.2f}** (95% CI {lo:.2f}–{hi:.2f}) — the chance that a random exceedance "
        f"day got a bigger rain/flow penalty than a random clean day. 0.5 is a coin flip, 1.0 is "
        f"perfect.\n"
    )
    season = df[in_season]
    sy = season["exceeds"].to_numpy(dtype=bool)
    s_auc = auc(-season["penalty"].to_numpy(), sy)
    s_lo, s_hi = auc_ci(-season["penalty"].to_numpy(), sy, rng)
    out.append(
        f"Swim season only (May–Sep): AUC {s_auc:.2f} (95% CI {s_lo:.2f}–{s_hi:.2f}) on "
        f"{len(season)} samples with just {int(sy.sum())} exceedances "
        f"({sy.mean():.1%}) — too few to grade summer on its own with confidence.\n"
    )

    # 2. What the dashboard would have said
    out.append("## 2. What the dashboard would have shown\n")
    ratings = ["Excellent", "Good", "Caution", "Avoid Swimming"]
    rows = []
    for r in ratings:
        mask = (df["rating"] == r).to_numpy()
        ex, clean = int((mask & y).sum()), int((mask & ~y).sum())
        rate = f"{ex / (ex + clean):.1%}" if ex + clean else "—"
        rows.append({"Rating": r, "Exceedance days": ex, "Clean days": clean, "Exceedance rate": rate})
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 3. Operating points
    out.append("## 3. Every possible warning threshold\n")
    out.append(
        "If the dashboard warned whenever the rain/flow penalty reached a given level: how many "
        "exceedances it would catch, and how many clean May–Sep days it would cry wolf on.\n"
    )
    rows = []
    for t in sorted(df["penalty"].unique()):
        if t >= 0:
            continue
        flag = (df["penalty"] <= t).to_numpy()
        tp, fp = int((flag & y).sum()), int((flag & ~y).sum())
        season_fpr = (flag & ~y & in_season).sum() / max((~y & in_season).sum(), 1)
        rows.append({
            "Warn at penalty ≤": int(t),
            "Exceedances caught": f"{tp}/{n_pos} ({tp / n_pos:.0%})",
            "Clean days flagged": f"{fp}/{n_neg} ({fp / n_neg:.1%})",
            "Precision": f"{tp / (tp + fp):.0%}" if tp + fp else "—",
            "False alarms / season": f"≈{season_fpr * SEASON_DAYS:.0f} days",
        })
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 4. Per site
    out.append("## 4. By site\n")
    rows = []
    for site, g in df.groupby("site"):
        gy = g["exceeds"].to_numpy(dtype=bool)
        rows.append({
            "Site": site, "Samples": len(g), "Exceedances": int(gy.sum()),
            "AUC": f"{auc(-g['penalty'].to_numpy(), gy):.2f}",
        })
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 5. Univariate signal
    out.append("## 5. Where the signal is: each input on its own\n")
    out.append(
        "AUC of each candidate input by itself (rows missing that input are skipped). Direction is "
        "which way it points toward exceedances; a CI that includes 0.50 means no reliable signal.\n"
    )
    rows = []
    for col, label in CANDIDATES.items():
        sub = df[df[col].notna()]
        sy = sub["exceeds"].to_numpy(dtype=bool)
        x = sub[col].to_numpy(dtype=float)
        a = auc(x, sy)
        direction = "higher → more" if a >= 0.5 else "lower → more"
        x_oriented = x if a >= 0.5 else -x
        lo, hi = auc_ci(x_oriented, sy, rng)
        rows.append({
            "Input": label, "n": len(sub), "Exceedances": int(sy.sum()),
            "AUC": f"{max(a, 1 - a):.2f}", "95% CI": f"{lo:.2f}–{hi:.2f}", "Direction": direction,
        })
    rows.sort(key=lambda r: r["AUC"], reverse=True)
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 6. Exceedance by month
    out.append("## 6. Exceedances by month\n")
    by_month = df.groupby("month")["exceeds"].agg(["sum", "count"])
    rows = [{"Month": m, "Samples": int(r["count"]), "Exceedances": int(r["sum"]),
             "Rate": f"{r['sum'] / r['count']:.1%}"} for m, r in by_month.iterrows()]
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 7. Every exceedance
    out.append("## 7. Every exceedance, and what the dashboard would have said\n")
    ex = df[y].sort_values("sampled_at")
    dry = int((ex["rain_7d"] < 0.25).sum())
    out.append(
        f"{dry} of {n_pos} exceedances followed less than 0.25\" of rain over the prior 7 days — "
        f"out of reach for any rain-based rule; other causes (e.g. sewage spills) would have to "
        f"explain those.\n"
    )
    rows = [{
        "Sampled": r.sampled_at[:10], "Site": r.site, "MPN": int(r.mpn),
        "Rain 24h": f'{r.rain_24h:.2f}"', "Rain 72h": f'{r.rain_72h:.2f}"', "Rain 7d": f'{r.rain_7d:.2f}"',
        "Flow ÷ p80": f"{r.flow_ratio:.2f}" if not math.isnan(r.flow_ratio) else "—",
        "Penalty": int(r.penalty), "Rating shown": r.rating,
    } for r in ex.itertuples(index=False)]
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    report = "\n".join(out)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report)
    print(report)
    print(f"\nWrote {REPORT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
