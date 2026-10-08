"""
Does radar rain predict bacteria exceedances better than KEWN's gauge?

KEWN sits miles from both DEQ sites and has gone dark for weeks at a time;
radar estimates rain over each site itself. This refits the deployed model
(rain + flow + season + site, logistic) with each rain source in turn and
grades them out of sample on the same samples -- 2014 onward, where MRMS
radar exists, and only samples whose KEWN rain checked out against NOAA's
daily record, so a dead gauge can't hand radar the win.

All three sources use the same daily windows -- the 3 full days before the
sample day, and the 4 before those -- so resolution isn't what's compared.
(The deployed model uses hourly KEWN windows ending at sample time; it's
listed too, for reference.)

Run from backend/ after build_dataset:
    python -m calibration.compare_rain
Prints the report and writes calibration/reports/rain_sources.md.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from calibration.baseline import md_table
from calibration.fit_model import (
    DATA, FEATURE_SETS, Climatology, Logistic, auc, auc_ci, brier, log_loss, loyo, paired_bootstrap,
)

HERE = Path(__file__).resolve().parent
REPORT = HERE / "reports" / "rain_sources.md"
FULL = FEATURE_SETS["rain + flow + season + site"]

SOURCES = {
    "KEWN gauge (daily)": "kewn",
    "MRMS radar at site": "mrms",
    "Stage IV radar at site": "stage4",
}


def with_rain(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """The dataset with one source's daily rain in the columns the model reads."""
    out = df.copy()
    out["rain_72h"] = df[f"{prefix}_d1_3"]
    out["rain_7d"] = df[f"{prefix}_d1_3"] + df[f"{prefix}_d4_7"]
    return out


def main() -> None:
    rng = np.random.default_rng(0)
    df = pd.read_csv(DATA)
    cols = [f"{p}_{w}" for p in SOURCES.values() for w in ("d1_3", "d4_7")]
    df = df[(df["rain_check"] == "ok") & df[cols].notna().all(axis=1)].reset_index(drop=True)
    y = df["exceeds"].to_numpy(dtype=float)
    n_pos = int(y.sum())

    preds = {"Base rate only": loyo(Climatology, df)}
    preds["Deployed: KEWN hourly, to sample time"] = loyo(lambda: Logistic(FULL), df)
    for label, prefix in SOURCES.items():
        preds[label] = loyo(lambda: Logistic(FULL), with_rain(df, prefix))

    clim = brier(preds["Base rate only"], y)
    rows = []
    for label, p in preds.items():
        lo, hi = auc_ci(p, y, rng) if label != "Base rate only" else (np.nan, np.nan)
        rows.append({
            "Rain source": label,
            "AUC": "0.50" if label == "Base rate only" else f"{auc(p, y):.2f}",
            "AUC 95% CI": "—" if label == "Base rate only" else f"{lo:.2f}–{hi:.2f}",
            "Brier skill": f"{1 - brier(p, y) / clim:+.1%}",
            "Log loss": f"{log_loss(p, y):.4f}",
        })

    corr = df[["kewn_d1_3", "mrms_d1_3", "stage4_d1_3"]].corr().round(2)
    out = [
        "# Rain source: KEWN gauge vs radar at the sampling site\n",
        f"{len(df)} samples ({df['year'].min()}–{df['year'].max()}) with confirmed KEWN rain and radar "
        f"coverage; {n_pos} exceedances. Same model and features throughout — only the rain source "
        f"changes. Leave-one-year-out.\n",
        md_table(pd.DataFrame(rows)) + "\n",
        "## Head to head vs KEWN (same daily windows, same days)\n",
    ]
    kewn = preds["KEWN gauge (daily)"]
    for label in ("MRMS radar at site", "Stage IV radar at site"):
        d = paired_bootstrap(preds[label], kewn, y, rng)
        out.append(
            f"- **{label}**: AUC {auc(preds[label], y):.2f} vs {auc(kewn, y):.2f} "
            f"(difference 95% CI {d['auc'][0]:+.2f} to {d['auc'][1]:+.2f}); Brier difference "
            f"95% CI {d['brier'][0]:+.4f} to {d['brier'][1]:+.4f} (negative favors radar)\n"
        )
    out.append("\n## How closely the sources agree (3-day rain, correlation)\n")
    out.append(md_table(corr.reset_index().rename(columns={"index": ""})) + "\n")

    report = "\n".join(out)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report)
    print(report)
    print(f"\nWrote {REPORT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
