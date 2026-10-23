# Do new predictors improve the bacteria-risk model?

Each row adds inputs to the current model (rain + flow + season + site) and is graded leave-one-year-out on exactly the same samples as the current model. Lower Brier and log loss are better. **P(better)** is the share of 2,000 bootstrap resamples where the row beats the current model on Brier. **Adopt** requires better LOYO Brier and log loss, a better forward test (fit ≤2016, predict later), and P(better) ≥ 90% — set before the results were seen.

## All samples with wind, dry-spell and tide data (868 samples, 35 exceedances, 1998–2026)

| Inputs | AUC | Brier | Log loss | Forward Brier | P(better) | Adopt? |
|---|---|---|---|---|---|---|
| current model | 0.780 | 0.03346 | 0.1412 | 0.03986 | — | — |
| + wind | 0.796 | 0.03272 | 0.1382 | 0.03874 | 87% | no |
| + dry spell | 0.778 | 0.03402 | 0.1432 | 0.04190 | 0% | no |
| + tide | 0.767 | 0.03421 | 0.1451 | 0.04156 | 2% | no |
| + wind + dry spell + tide | 0.782 | 0.03392 | 0.1435 | 0.04297 | 27% | no |

## Samples with Pollocksville river level too (644 samples, 26 exceedances, 2007–2026)

| Inputs | AUC | Brier | Log loss | Forward Brier | P(better) | Adopt? |
|---|---|---|---|---|---|---|
| current model | 0.720 | 0.03629 | 0.1548 | 0.04654 | — | — |
| + river level | 0.717 | 0.03595 | 0.1544 | 0.04644 | 73% | no |
| + wind | 0.743 | 0.03589 | 0.1519 | 0.04613 | 71% | no |
| + wind + river level + dry spell + tide | 0.724 | 0.03558 | 0.1539 | 0.04711 | 68% | no |
