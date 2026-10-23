"""
Do new predictors make the bacteria-risk model more accurate?

Each hypothesis adds a small, pre-chosen set of inputs to the deployed model
(rain + flow + season + site, logistic) and is graded out of sample on the
same samples as the model without it:

  wind        NE wind pushes Pamlico Sound water up the Trent and over the
              shoreline: mean wind speed along the NE direction over 72h
  river level high water reaches shoreline sources: Pollocksville gauge height
              over the prior 24h and its 3-day change (USGS record: 2007 on)
  dry spell   rain after a long dry spell flushes more bacteria ("first
              flush"): dry days before the rain, and that times recent rain
  tide        NOAA's predicted tide at sample time and the day's range

Adoption rule, fixed before looking at results: a set is adopted only if it
beats the current model on leave-one-year-out Brier score AND log loss, on
the forward test (fit <=2016, predict 2017+), AND improves Brier in at least
90% of paired bootstrap resamples. With ~35 exceedances, anything weaker is
indistinguishable from noise.

Run from backend/ after build_dataset:
    python -m calibration.test_predictors
Prints the report and writes calibration/reports/predictors.md.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from calibration.baseline import md_table
from calibration.fit_model import DATA, FEATURE_SETS, FORWARD_SPLIT_YEAR, L2, auc, brier, design, log_loss, loyo

HERE = Path(__file__).resolve().parent
REPORT = HERE / "reports" / "predictors.md"
BASE = FEATURE_SETS["rain + flow + season + site"]
BOOTSTRAP = 2000

HYPOTHESES = {
    "wind": lambda d: pd.DataFrame({"wind_ne_72h": d["wind_ne_72h"]}),
    "river level": lambda d: pd.DataFrame({
        "level": d["level_plln_24h"],
        "level_change": d["level_plln_change_3d"],
    }),
    "dry spell": lambda d: pd.DataFrame({
        "dry": np.log1p(d["dry_days_before"]),
        "rain_after_dry": np.log1p(d["rain_72h"]) * np.log1p(d["dry_days_before"]),
    }),
    "tide": lambda d: pd.DataFrame({"tide": d["tide_ft"], "tide_range": d["tide_range_day"]}),
}


class Extended:
    """The deployed model's inputs plus extra columns, same regularization."""

    def __init__(self, extras: list[str]):
        self.extras = extras

    def _x(self, df):
        cols = [design(df, BASE)]
        for name in self.extras:
            cols.append(HYPOTHESES[name](df).to_numpy(dtype=float))
        return np.column_stack(cols)

    def fit(self, df):
        X = self._x(df)
        self.scaler = StandardScaler().fit(X)
        self.clf = LogisticRegression(C=1 / L2, max_iter=2000).fit(
            self.scaler.transform(X), df["exceeds"].to_numpy(dtype=int)
        )
        return self

    def predict(self, df):
        return self.clf.predict_proba(self.scaler.transform(self._x(df)))[:, 1]


def compare(df: pd.DataFrame, candidates: list[list[str]], rng) -> list[dict]:
    y = df["exceeds"].to_numpy(dtype=float)
    base_p = loyo(lambda: Extended([]), df)
    train = (df["year"] <= FORWARD_SPLIT_YEAR).to_numpy()
    fwd_y = y[~train]
    base_fwd = Extended([]).fit(df[train]).predict(df[~train])
    rows = [{
        "Inputs": "current model", "AUC": f"{auc(base_p, y):.3f}", "Brier": f"{brier(base_p, y):.5f}",
        "Log loss": f"{log_loss(base_p, y):.4f}", "Forward Brier": f"{brier(base_fwd, fwd_y):.5f}",
        "P(better)": "—", "Adopt?": "—",
    }]
    for extras in candidates:
        p = loyo(lambda e=extras: Extended(e), df)
        fwd = Extended(extras).fit(df[train]).predict(df[~train])
        wins, n = 0, len(y)
        for _ in range(BOOTSTRAP):
            idx = rng.integers(0, n, n)
            wins += brier(p[idx], y[idx]) < brier(base_p[idx], y[idx])
        p_better = wins / BOOTSTRAP
        adopt = (
            brier(p, y) < brier(base_p, y)
            and log_loss(p, y) < log_loss(base_p, y)
            and brier(fwd, fwd_y) < brier(base_fwd, fwd_y)
            and p_better >= 0.9
        )
        rows.append({
            "Inputs": "+ " + " + ".join(extras), "AUC": f"{auc(p, y):.3f}", "Brier": f"{brier(p, y):.5f}",
            "Log loss": f"{log_loss(p, y):.4f}", "Forward Brier": f"{brier(fwd, fwd_y):.5f}",
            "P(better)": f"{p_better:.0%}", "Adopt?": "**yes**" if adopt else "no",
        })
    return rows


def main() -> None:
    rng = np.random.default_rng(0)
    df = pd.read_csv(DATA)
    df = df[df["rain_check"] == "ok"]
    needs = ["wind_ne_72h", "dry_days_before", "tide_ft", "tide_range_day", "flow_ratio"]
    full = df.dropna(subset=needs).reset_index(drop=True)
    with_level = full.dropna(subset=["level_plln_24h", "level_plln_change_3d"]).reset_index(drop=True)

    out = ["# Do new predictors improve the bacteria-risk model?\n"]
    out.append(
        "Each row adds inputs to the current model (rain + flow + season + site) and is graded "
        "leave-one-year-out on exactly the same samples as the current model. Lower Brier and log "
        "loss are better. **P(better)** is the share of 2,000 bootstrap resamples where the row beats "
        "the current model on Brier. **Adopt** requires better LOYO Brier and log loss, a better "
        f"forward test (fit ≤{FORWARD_SPLIT_YEAR}, predict later), and P(better) ≥ 90% — set before "
        "the results were seen.\n"
    )
    for title, data, candidates in [
        (
            f"All samples with wind, dry-spell and tide data ({len(full)} samples, "
            f"{int(full['exceeds'].sum())} exceedances, {full['year'].min()}–{full['year'].max()})",
            full,
            [["wind"], ["dry spell"], ["tide"], ["wind", "dry spell", "tide"]],
        ),
        (
            f"Samples with Pollocksville river level too ({len(with_level)} samples, "
            f"{int(with_level['exceeds'].sum())} exceedances, {with_level['year'].min()}–{with_level['year'].max()})",
            with_level,
            [["river level"], ["wind"], ["wind", "river level", "dry spell", "tide"]],
        ),
    ]:
        out.append(f"## {title}\n")
        out.append(md_table(pd.DataFrame(compare(data, candidates, rng))) + "\n")

    report = "\n".join(out)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report)
    print(report)
    print(f"\nWrote {REPORT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
