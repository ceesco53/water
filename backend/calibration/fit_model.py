"""
Step 4 of score calibration: fit and test a bacteria-risk model.

Predicts the chance that a sample drawn this morning would meet or exceed
NC's single-sample standard (104 MPN) from what's known before it's drawn:
recent rain, Trent River flow, and time of year. Two model types are
compared against the original dashboard formula and the plain base rate:

  logistic  yes/no exceedance -- L2-regularized logistic regression
  tobit     censored regression on log10(MPN) -- learns from every sample's
            count, not just the 35 exceedances, treating the two-thirds of
            samples at the lab's detection limit (<10) as "10 or less"
            rather than as exactly 10

Everything is tested out of sample: leave-one-year-out (each year predicted
by a model that never saw it), plus a forward test (fit on 1998-2016,
predict 2017-2026). Samples whose rain couldn't be confirmed are excluded,
as in the baseline.

The candidate with the best out-of-sample Brier score is refit on all
samples and written, with the warning policy below, to
app/data/bacteria_risk_model.json -- the file the dashboard loads. Picking it
from the same cross-validation flatters it slightly; the forward test is the
more honest check. Inputs are built by app.risk_model.features, the same
function the live dashboard calls, so training and serving can't drift.

Warning policy (decided 2026-10-07): a big summer storm -- 2"+ of rain in
72h, May-Sep -- always rates at least Caution, and the model's Caution
probability is the lowest that keeps warnings, floor included, on no more
than 5% of clean days. Retraining re-derives the probability for that same
policy.

Run from backend/ after build_dataset:
    python -m calibration.fit_model
Prints the report and writes calibration/reports/model.md.
"""
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app import risk_model
from app.risk_model import features as model_features
from calibration.baseline import auc, md_table, replay
from calibration.build_dataset import EXCEEDANCE_MPN

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "samples.csv"
REPORT = HERE / "reports" / "model.md"
MODEL_OUT = HERE.parent / "app" / "data" / "bacteria_risk_model.json"

DETECTION_LIMIT_MPN = 10  # Enterolert's lower limit; reported as 9 or 10
L2 = 1.0                  # same strength for both models (logistic C = 1/L2)
FORWARD_SPLIT_YEAR = 2016
BOOTSTRAP = 2000
LIVE_SITE = "C100A"       # River Bend is predicted as Union Point, the nearest site

SUMMER_FLOOR = {"months": [5, 6, 7, 8, 9], "rain_72h_in": 2.0}
TARGET_CLEAN_FLAG_RATE = 0.05

# Each feature is computable live: rain from KEWN, flow from the Trenton
# gauge vs its day-of-year p80, season from the date. Transforms live in
# app.risk_model.features; these are just their descriptions.
FEATURES = {
    "rain_0_3d": "log(1 + rain in the 72h before, in)",
    "rain_3_7d": "log(1 + rain 3–7 days before, in)",
    "flow": "log(Trenton flow ÷ day-of-year p80)",
    "season_sin": "sin(2π · day of year / 365.25)",
    "season_cos": "cos(2π · day of year / 365.25)",
    "union_point": "1 at Union Point (C100A), 0 at NW Creek (C99)",
}

FEATURE_SETS = {
    "rain": ["rain_0_3d", "rain_3_7d"],
    "rain + flow": ["rain_0_3d", "rain_3_7d", "flow"],
    "rain + flow + season": ["rain_0_3d", "rain_3_7d", "flow", "season_sin", "season_cos"],
    "rain + flow + season + site": ["rain_0_3d", "rain_3_7d", "flow", "season_sin", "season_cos", "union_point"],
}


def design(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    rows = []
    for r in df.itertuples(index=False):
        f = model_features(r.rain_72h, r.rain_7d, r.flow_ratio, r.doy,
                           union_point=1.0 if r.site == "C100A" else 0.0)
        rows.append([np.nan if f[c] is None else f[c] for c in cols])
    return np.array(rows, dtype=float)


# ── Models: fit(df) -> self, predict(df) -> P(exceed) ─────────────────────────

class Climatology:
    def fit(self, df):
        self.p = df["exceeds"].mean()
        return self

    def predict(self, df):
        return np.full(len(df), self.p)


class FormulaRates:
    """
    The original formula, turned into probabilities by a one-variable logistic fit
    on its rain/flow penalty (Platt scaling). Monotone, so it keeps the
    formula's own ranking (AUC) intact -- it's the best-calibrated version of
    the formula, which makes it the fair yardstick for the model's Brier.
    (Mapping each penalty level to its raw training rate was tried first;
    sparse levels came out out of order and scrambled the ranking.)
    """

    def fit(self, df):
        self.clf = LogisticRegression(C=1 / L2, max_iter=1000).fit(
            df[["penalty"]].to_numpy(dtype=float), df["exceeds"].to_numpy(dtype=int)
        )
        return self

    def predict(self, df):
        return self.clf.predict_proba(df[["penalty"]].to_numpy(dtype=float))[:, 1]


class Logistic:
    kind = "logistic"

    def __init__(self, cols):
        self.cols = cols

    def fit(self, df):
        X = design(df, self.cols)
        self.scaler = StandardScaler().fit(X)
        self.clf = LogisticRegression(C=1 / L2, max_iter=1000).fit(
            self.scaler.transform(X), df["exceeds"].to_numpy(dtype=int)
        )
        return self

    def predict(self, df):
        return self.clf.predict_proba(self.scaler.transform(design(df, self.cols)))[:, 1]

    def export(self) -> dict:
        return {
            "intercept": float(self.clf.intercept_[0]),
            "coef": [float(c) for c in self.clf.coef_[0]],
        }


class Tobit:
    kind = "tobit"

    def __init__(self, cols):
        self.cols = cols

    def fit(self, df):
        X = design(df, self.cols)
        self.scaler = StandardScaler().fit(X)
        Xs = np.column_stack([np.ones(len(df)), self.scaler.transform(X)])
        mpn = df["mpn"].to_numpy(dtype=float)
        y = np.log10(np.maximum(mpn, 1.0))
        censored = mpn <= DETECTION_LIMIT_MPN
        limit = math.log10(DETECTION_LIMIT_MPN)

        def nll(params):
            beta, sigma = params[:-1], math.exp(params[-1])
            mu = Xs @ beta
            ll = norm.logpdf(y[~censored], mu[~censored], sigma).sum()
            ll += norm.logcdf((limit - mu[censored]) / sigma).sum()
            return -ll + 0.5 * L2 * (beta[1:] ** 2).sum()

        x0 = np.zeros(Xs.shape[1] + 1)
        x0[0], x0[-1] = y.mean(), math.log(y.std() or 1.0)
        res = minimize(nll, x0, method="L-BFGS-B")
        self.beta, self.sigma = res.x[:-1], math.exp(res.x[-1])
        return self

    def mean_log10(self, df):
        Xs = np.column_stack([np.ones(len(df)), self.scaler.transform(design(df, self.cols))])
        return Xs @ self.beta

    def predict(self, df):
        z = (math.log10(EXCEEDANCE_MPN) - self.mean_log10(df)) / self.sigma
        return norm.sf(z)

    def export(self) -> dict:
        return {
            "intercept": float(self.beta[0]),
            "coef": [float(c) for c in self.beta[1:]],
            "sigma": float(self.sigma),
        }


# ── Evaluation ───────────────────────────────────────────────────────────────

def loyo(factory, df: pd.DataFrame) -> np.ndarray:
    """Leave-one-year-out predictions: each year scored by a model fit on every other year."""
    preds = np.full(len(df), np.nan)
    for year in sorted(df["year"].unique()):
        test = (df["year"] == year).to_numpy()
        preds[test] = factory().fit(df[~test]).predict(df[test])
    return preds


def brier(p, y) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p, y) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def paired_bootstrap(p_a, p_b, y, rng) -> dict:
    """95% CIs for AUC(a) - AUC(b) and Brier(a) - Brier(b), resampling the same days for both."""
    d_auc, d_brier = [], []
    n = len(y)
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        if y[idx].sum() == 0:
            continue
        d_auc.append(auc(p_a[idx], y[idx]) - auc(p_b[idx], y[idx]))
        d_brier.append(brier(p_a[idx], y[idx]) - brier(p_b[idx], y[idx]))
    return {
        "auc": (float(np.percentile(d_auc, 2.5)), float(np.percentile(d_auc, 97.5))),
        "brier": (float(np.percentile(d_brier, 2.5)), float(np.percentile(d_brier, 97.5))),
    }


def solve_caution_probability(p, floor, y) -> tuple[float, np.ndarray]:
    """Lowest Caution probability (0.5% steps) that keeps warnings, floor included, within the clean-day target."""
    clean = ~y
    for line in np.round(np.arange(0.005, 0.5, 0.005), 3):
        flagged = (p >= line) | floor
        if (flagged & clean).sum() / clean.sum() <= TARGET_CLEAN_FLAG_RATE:
            return float(line), flagged
    raise ValueError("the summer floor alone flags more clean days than the target allows")


def auc_ci(p, y, rng) -> tuple[float, float]:
    stats = []
    n = len(y)
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        if y[idx].sum():
            stats.append(auc(p[idx], y[idx]))
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def main() -> None:
    rng = np.random.default_rng(0)
    df = pd.read_csv(DATA)
    df = df[df["rain_check"] == "ok"].reset_index(drop=True)
    df["penalty"] = df.apply(lambda r: replay(r)[2], axis=1)
    y = df["exceeds"].to_numpy(dtype=float)
    yb = y.astype(bool)
    n_pos = int(y.sum())

    candidates: dict[str, tuple] = {}  # label -> (factory, kind, cols)
    for set_name, cols in FEATURE_SETS.items():
        candidates[f"Logistic: {set_name}"] = (lambda c=cols: Logistic(c), "logistic", cols)
        candidates[f"Tobit: {set_name}"] = (lambda c=cols: Tobit(c), "tobit", cols)

    oof = {
        "Base rate only": loyo(Climatology, df),
        "Original formula (rescaled)": loyo(FormulaRates, df),
    }
    for label, (factory, _, _) in candidates.items():
        oof[label] = loyo(factory, df)

    clim_brier = brier(oof["Base rate only"], y)
    formula_auc = auc(-df["penalty"].to_numpy(), y)
    rows = []
    for label, p in oof.items():
        # The formula's ranking needs no fitting, so its AUC is the raw
        # penalty's. Pooling per-year rescalings instead would re-rank the
        # ~800 tied zero-penalty days by which year was held out, which
        # understates it (0.65 vs 0.74).
        ranked = -df["penalty"].to_numpy() if label == "Original formula (rescaled)" else p
        lo, hi = auc_ci(ranked, y, rng) if label != "Base rate only" else (math.nan, math.nan)
        rows.append({
            "Model": label,
            "AUC": "0.50" if label == "Base rate only" else f"{auc(ranked, y):.2f}",
            "AUC 95% CI": "—" if label == "Base rate only" else f"{lo:.2f}–{hi:.2f}",
            "Brier": f"{brier(p, y):.4f}",
            "Brier skill": f"{1 - brier(p, y) / clim_brier:+.1%}",
            "Log loss": f"{log_loss(p, y):.4f}",
        })

    best_label = min(candidates, key=lambda k: brier(oof[k], y))
    best_factory, best_kind, best_cols = candidates[best_label]
    p_best = oof[best_label]

    out: list[str] = []
    out.append("# Bacteria-risk model: does it beat the original formula?\n")
    out.append(
        f"Target: the chance a sample drawn that morning meets or exceeds NC's standard "
        f"(≥{EXCEEDANCE_MPN} MPN). {len(df)} samples with confirmed rain, {n_pos} exceedances "
        f"({y.mean():.1%}). Every number below is **out of sample** — leave-one-year-out unless "
        f"noted.\n"
    )

    out.append("## 1. All candidates\n")
    out.append(
        "**AUC**: ranking quality (0.5 coin flip, 1.0 perfect). **Brier**: mean squared error of "
        "the probabilities — lower is better; **Brier skill** is the improvement over always "
        "predicting the base rate. The original formula had no probabilities of its own, so for Brier "
        "it's rescaled with a one-variable logistic fit on its penalty; its AUC is the raw "
        "penalty's, which needs no fitting.\n"
    )
    out.append(md_table(pd.DataFrame(rows)) + "\n")
    out.append(f"Best by Brier: **{best_label}** — refit on all samples and exported.\n")

    # 2. Head to head
    out.append("## 2. Best model vs the original formula, same days\n")
    formula_rates = oof["Original formula (rescaled)"]
    cmp_auc = paired_bootstrap(p_best, -df["penalty"].to_numpy(), y, rng)["auc"]
    cmp_brier = paired_bootstrap(p_best, formula_rates, y, rng)["brier"]
    out.append(
        f"- AUC {auc(p_best, y):.2f} vs {formula_auc:.2f}: difference 95% CI "
        f"{cmp_auc[0]:+.2f} to {cmp_auc[1]:+.2f}\n"
        f"- Brier {brier(p_best, y):.4f} vs {brier(formula_rates, y):.4f}: difference 95% CI "
        f"{cmp_brier[0]:+.4f} to {cmp_brier[1]:+.4f} (negative favors the model)\n"
        "- A CI that straddles zero means the data can't tell them apart.\n"
    )

    # 3. Operating points at the formula's own false-alarm rates
    out.append("## 3. Same false alarms, more catches?\n")
    out.append(
        "At each of the formula's warning levels, the model's threshold is set to flag the same "
        "share of clean days; then compare how many exceedances each catches.\n"
    )
    neg_scores = p_best[~yb]
    rows = []
    for t in (-28, -18, -10):
        f_flag = (df["penalty"] <= t).to_numpy()
        fpr = (f_flag & ~yb).sum() / (~yb).sum()
        tau = np.quantile(neg_scores, 1 - fpr)
        m_flag = p_best >= tau
        rows.append({
            "Formula warns at": f"penalty ≤ {t}",
            "Clean days flagged": f"{fpr:.1%}",
            "Formula catches": f"{(f_flag & yb).sum()}/{n_pos}",
            "Model catches": f"{(m_flag & yb).sum()}/{n_pos}",
            "Model threshold": f"P ≥ {tau:.1%}",
        })
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 4. Calibration
    out.append("## 4. Are its probabilities honest?\n")
    out.append("Out-of-sample predictions grouped by predicted chance, against what actually happened.\n")
    bins = [0, 0.02, 0.05, 0.10, 0.20, 1.0]
    labels = ["<2%", "2–5%", "5–10%", "10–20%", "≥20%"]
    cut = pd.cut(p_best, bins=bins, labels=labels, right=False)
    rows = []
    for lab in labels:
        m = (cut == lab)
        if m.sum() == 0:
            continue
        rows.append({
            "Predicted": lab, "Days": int(m.sum()), "Mean predicted": f"{p_best[m].mean():.1%}",
            "Exceedances": int(y[m].sum()), "Observed rate": f"{y[m].mean():.1%}",
        })
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 5. Forward test
    out.append(f"## 5. Forward test: fit on ≤{FORWARD_SPLIT_YEAR}, predict {FORWARD_SPLIT_YEAR + 1}+\n")
    train = df["year"] <= FORWARD_SPLIT_YEAR
    test = ~train
    yt = y[test.to_numpy()]
    rows = []
    for label, factory in [
        ("Base rate only", Climatology),
        ("Original formula (rescaled)", FormulaRates),
        (best_label, best_factory),
    ]:
        p = factory().fit(df[train]).predict(df[test])
        rows.append({
            "Model": label,
            "AUC": "0.50" if label == "Base rate only" else f"{auc(p, yt):.2f}",
            "Brier": f"{brier(p, yt):.4f}",
            "Brier skill": f"{1 - brier(p, yt) / brier(np.full(len(yt), y[train.to_numpy()].mean()), yt):+.1%}",
        })
    out.append(
        f"{int(test.sum())} test samples, {int(yt.sum())} exceedances.\n\n" + md_table(pd.DataFrame(rows)) + "\n"
    )

    # Final fit on everything
    final = best_factory().fit(df)

    # 6. What it learned
    out.append("## 6. What the model learned\n")
    exported = final.export()
    unit = "change in log-odds" if best_kind == "logistic" else "change in log10(MPN)"
    rows = [{"Input": FEATURES[c], f"Per 1 SD ({unit})": f"{b:+.2f}"}
            for c, b in zip(best_cols, exported["coef"])]
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    out.append("Predicted chance of exceeding at Union Point, no rain 3–7 days before:\n")
    rows = []
    for season, doy in [("Mid-January", 15), ("Mid-April", 105), ("Mid-July", 196), ("Mid-October", 288)]:
        for flow_label, ratio in [("typical flow", 0.4), ("high flow", 1.5)]:
            row = {"When": season, "Flow": flow_label}
            for rain in (0.0, 0.5, 1.0, 2.0):
                scenario = pd.DataFrame([{
                    "rain_72h": rain, "rain_7d": rain, "flow_ratio": ratio, "doy": doy, "site": LIVE_SITE,
                }])
                row[f'{rain:g}" in 72h'] = f"{final.predict(scenario)[0]:.1%}"
            rows.append(row)
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    # 7. Warning policy, solved on the out-of-sample predictions
    floor = (df["month"].isin(SUMMER_FLOOR["months"])
             & (df["rain_72h"] >= SUMMER_FLOOR["rain_72h_in"])).to_numpy()
    caution_p, flagged = solve_caution_probability(p_best, floor, yb)
    clean_rate = (flagged & ~yb).sum() / (~yb).sum()
    caught = int((flagged & yb).sum())
    by_model = int(((p_best >= caution_p) & yb).sum())
    by_floor_only = int((floor & (p_best < caution_p) & yb).sum())
    season = df["month"].isin(range(5, 10)).to_numpy()
    season_false = (flagged & ~yb & season).sum() / max((~yb & season).sum(), 1) * 153
    legacy_rows = []
    for t in sorted(df["penalty"].unique()):
        f = (df["penalty"] <= t).to_numpy()
        legacy_rows.append((abs((f & ~yb).sum() / (~yb).sum() - clean_rate), t, f))
    _, legacy_t, legacy_f = min(legacy_rows, key=lambda r: r[0])
    out.append("## 7. Warning policy\n")
    out.append(
        f"Big summer storms (≥{SUMMER_FLOOR['rain_72h_in']:g}\" of rain in 72h, May–Sep) always rate "
        f"Caution; the model's Caution line is the lowest probability that keeps all warnings on "
        f"≤{TARGET_CLEAN_FLAG_RATE:.0%} of clean days.\n\n"
        f"- Caution line: **P ≥ {caution_p:.1%}**\n"
        f"- Clean days flagged: {clean_rate:.1%} (≈{season_false:.0f} clean May–Sep days per season)\n"
        f"- Exceedances caught: **{caught}/{n_pos}** ({by_model} by the model, "
        f"{by_floor_only} more by the summer floor)\n"
        f"- Original formula at its nearest rate (penalty ≤ {int(legacy_t)}): "
        f"{(legacy_f & ~yb).sum() / (~yb).sum():.1%} of clean days flagged, "
        f"{int((legacy_f & yb).sum())}/{n_pos} caught\n"
    )

    MODEL_OUT.write_text(json.dumps({
        "model": best_kind,
        "label": best_label,
        "target": f"P(enterococcus >= {EXCEEDANCE_MPN} MPN/100mL), predicted as site {LIVE_SITE}",
        "features": [{"name": c, "transform": FEATURES[c]} for c in best_cols],
        "scaler_mean": [float(v) for v in final.scaler.mean_],
        "scaler_scale": [float(v) for v in final.scaler.scale_],
        **exported,
        "exceedance_mpn": EXCEEDANCE_MPN,
        "policy": {
            "caution_probability": caution_p,
            "summer_floor": SUMMER_FLOOR,
            "target_clean_flag_rate": TARGET_CLEAN_FLAG_RATE,
            "backtest": {
                "clean_flag_rate": round(float(clean_rate), 4),
                "exceedances_caught": caught,
                "exceedances": n_pos,
            },
        },
        "trained": {
            "date": date.today().isoformat(),
            "samples": len(df),
            "exceedances": n_pos,
            "years": [int(df["year"].min()), int(df["year"].max())],
        },
        "validation": {
            "loyo_auc": round(auc(p_best, y), 3),
            "loyo_brier": round(brier(p_best, y), 5),
            "base_rate_brier": round(clim_brier, 5),
            "formula_auc": round(formula_auc, 3),
        },
    }, indent=2) + "\n")

    # Train/serve parity: the dashboard's own predict() on the exported file
    # must reproduce the fitted model on every Union Point sample.
    risk_model.load_model.cache_clear()
    union_point = df[df["site"] == LIVE_SITE]
    served = np.array([
        risk_model.predict(r.rain_72h, r.rain_7d, r.flow_ratio,
                           date.fromisoformat(r.sampled_at[:10]))["probability"]
        for r in union_point.itertuples(index=False)
    ])
    drift = float(np.max(np.abs(served - final.predict(union_point))))
    if drift > 1e-9:
        raise AssertionError(f"app.risk_model disagrees with the fitted model by up to {drift:.2e}")

    report = "\n".join(out)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report)
    print(report)
    print(f"\nWrote {REPORT.relative_to(HERE.parent)} and {MODEL_OUT.relative_to(HERE.parent)} "
          f"(app.risk_model reproduces it to within {drift:.0e})")


if __name__ == "__main__":
    main()
