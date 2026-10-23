# Bacteria-risk model: does it beat the original formula?

Target: the chance a sample drawn that morning meets or exceeds NC's standard (≥104 MPN). 886 samples with confirmed rain, 35 exceedances (4.0%). Every number below is **out of sample** — leave-one-year-out unless noted.

## 1. All candidates

**AUC**: ranking quality (0.5 coin flip, 1.0 perfect). **Brier**: mean squared error of the probabilities — lower is better; **Brier skill** is the improvement over always predicting the base rate. The original formula had no probabilities of its own, so for Brier it's rescaled with a one-variable logistic fit on its penalty; its AUC is the raw penalty's, which needs no fitting.

| Model | AUC | AUC 95% CI | Brier | Brier skill | Log loss |
|---|---|---|---|---|---|
| Base rate only | 0.50 | — | 0.0380 | +0.0% | 0.1674 |
| Original formula (rescaled) | 0.74 | 0.65–0.82 | 0.0363 | +4.5% | 0.1506 |
| Logistic: rain | 0.72 | 0.62–0.81 | 0.0373 | +1.8% | 0.1561 |
| Tobit: rain | 0.70 | 0.59–0.80 | 0.0374 | +1.5% | 0.1609 |
| Logistic: rain + flow | 0.74 | 0.64–0.83 | 0.0369 | +2.9% | 0.1536 |
| Tobit: rain + flow | 0.70 | 0.60–0.80 | 0.0369 | +2.8% | 0.1577 |
| Logistic: rain + flow + season | 0.76 | 0.66–0.85 | 0.0338 | +11.2% | 0.1435 |
| Tobit: rain + flow + season | 0.76 | 0.66–0.85 | 0.0348 | +8.4% | 0.1474 |
| Logistic: rain + flow + season + site | 0.78 | 0.69–0.86 | 0.0329 | +13.5% | 0.1391 |
| Tobit: rain + flow + season + site | 0.79 | 0.71–0.86 | 0.0341 | +10.2% | 0.1417 |

Best by Brier: **Logistic: rain + flow + season + site** — refit on all samples and exported.

## 2. Best model vs the original formula, same days

- AUC 0.78 vs 0.74: difference 95% CI -0.02 to +0.10
- Brier 0.0329 vs 0.0363: difference 95% CI -0.0075 to +0.0006 (negative favors the model)
- A CI that straddles zero means the data can't tell them apart.

## 3. Same false alarms, more catches?

At each of the formula's warning levels, the model's threshold is set to flag the same share of clean days; then compare how many exceedances each catches.

| Formula warns at | Clean days flagged | Formula catches | Model catches | Model threshold |
|---|---|---|---|---|
| penalty ≤ -28 | 1.3% | 4/35 | 8/35 | P ≥ 24.9% |
| penalty ≤ -18 | 5.3% | 10/35 | 14/35 | P ≥ 11.6% |
| penalty ≤ -10 | 24.2% | 24/35 | 21/35 | P ≥ 4.1% |

## 4. Are its probabilities honest?

Out-of-sample predictions grouped by predicted chance, against what actually happened.

| Predicted | Days | Mean predicted | Exceedances | Observed rate |
|---|---|---|---|---|
| <2% | 500 | 0.9% | 5 | 1.0% |
| 2–5% | 194 | 3.2% | 11 | 5.7% |
| 5–10% | 113 | 7.0% | 5 | 4.4% |
| 10–20% | 47 | 13.0% | 2 | 4.3% |
| ≥20% | 32 | 32.1% | 12 | 37.5% |

## 5. Forward test: fit on ≤2016, predict 2017+

349 test samples, 17 exceedances.

| Model | AUC | Brier | Brier skill |
|---|---|---|---|
| Base rate only | 0.50 | 0.0466 | +0.0% |
| Original formula (rescaled) | 0.75 | 0.0423 | +9.2% |
| Logistic: rain + flow + season + site | 0.79 | 0.0395 | +15.1% |

## 6. What the model learned

| Input | Per 1 SD (change in log-odds) |
|---|---|
| log(1 + rain in the 72h before, in) | +0.77 |
| log(1 + rain 3–7 days before, in) | +0.39 |
| log(Trenton flow ÷ day-of-year p80) | +0.30 |
| sin(2π · day of year / 365.25) | +0.03 |
| cos(2π · day of year / 365.25) | +0.85 |
| 1 at Union Point (C100A), 0 at NW Creek (C99) | +0.60 |

Predicted chance of exceeding at Union Point, no rain 3–7 days before:

| When | Flow | 0" in 72h | 0.5" in 72h | 1" in 72h | 2" in 72h |
|---|---|---|---|---|---|
| Mid-January | typical flow | 5.9% | 14.5% | 25.5% | 48.0% |
| Mid-January | high flow | 7.5% | 18.0% | 30.7% | 54.5% |
| Mid-April | typical flow | 1.4% | 3.6% | 7.1% | 17.0% |
| Mid-April | high flow | 1.8% | 4.7% | 9.0% | 21.0% |
| Mid-July | typical flow | 0.5% | 1.4% | 2.8% | 7.1% |
| Mid-July | high flow | 0.7% | 1.8% | 3.5% | 9.0% |
| Mid-October | typical flow | 2.3% | 6.0% | 11.5% | 25.9% |
| Mid-October | high flow | 3.0% | 7.7% | 14.4% | 31.2% |

## 7. Warning policy

Big summer storms (≥2" of rain in 72h, May–Sep) always rate Caution; the model's Caution line is the lowest probability that keeps all warnings on ≤5% of clean days.

- Caution line: **P ≥ 15.5%**
- Clean days flagged: 4.8% (≈7 clean May–Sep days per season)
- Exceedances caught: **13/35** (12 by the model, 1 more by the summer floor)
- Original formula at its nearest rate (penalty ≤ -18): 5.3% of clean days flagged, 10/35 caught
