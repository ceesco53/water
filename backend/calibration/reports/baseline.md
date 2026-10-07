# Baseline: how well does today's formula predict bacteria exceedances?

Graded on **882 NC DEQ samples** (1998–2026, Union Point and NW Creek) with rainfall confirmed against NOAA's daily record; 48 more were left out because KEWN's hourly rain disagreed with it or couldn't be checked. **35 exceeded** NC's single-sample standard (≥104 MPN) — 4.0%.

Each sample morning is scored the way the original dashboard did when it had no fresh bacteria result: its 24h/72h rain and upstream-flow rules (max penalty −45, frozen in `legacy_formula.py`), plus the −5 for missing bacteria data.

## 1. Overall

**AUC 0.74** (95% CI 0.66–0.83) — the chance that a random exceedance day got a bigger rain/flow penalty than a random clean day. 0.5 is a coin flip, 1.0 is perfect.

Swim season only (May–Sep): AUC 0.72 (95% CI 0.54–0.89) on 466 samples with just 10 exceedances (2.1%) — too few to grade summer on its own with confidence.

## 2. What the dashboard would have shown

| Rating | Exceedance days | Clean days | Exceedance rate |
|---|---|---|---|
| Excellent | 25 | 797 | 3.0% |
| Good | 6 | 39 | 13.3% |
| Caution | 4 | 11 | 26.7% |
| Avoid Swimming | 0 | 0 | — |

## 3. Every possible warning threshold

If the dashboard warned whenever the rain/flow penalty reached a given level: how many exceedances it would catch, and how many clean May–Sep days it would cry wolf on.

| Warn at penalty ≤ | Exceedances caught | Clean days flagged | Precision | False alarms / season |
|---|---|---|---|---|
| -35 | 2/35 (6%) | 2/847 (0.2%) | 50% | ≈1 days |
| -28 | 4/35 (11%) | 11/847 (1.3%) | 27% | ≈2 days |
| -25 | 5/35 (14%) | 18/847 (2.1%) | 22% | ≈4 days |
| -20 | 6/35 (17%) | 23/847 (2.7%) | 21% | ≈6 days |
| -18 | 10/35 (29%) | 45/847 (5.3%) | 18% | ≈11 days |
| -15 | 10/35 (29%) | 50/847 (5.9%) | 17% | ≈13 days |
| -10 | 24/35 (69%) | 206/847 (24.3%) | 10% | ≈45 days |
| -8 | 25/35 (71%) | 244/847 (28.8%) | 9% | ≈53 days |

## 4. By site

| Site | Samples | Exceedances | AUC |
|---|---|---|---|
| C100A | 432 | 26 | 0.78 |
| C99 | 450 | 9 | 0.65 |

## 5. Where the signal is: each input on its own

AUC of each candidate input by itself (rows missing that input are skipped). Direction is which way it points toward exceedances; a CI that includes 0.50 means no reliable signal.

| Input | n | Exceedances | AUC | 95% CI | Direction |
|---|---|---|---|---|---|
| Rain, 72h before | 882 | 35 | 0.73 | 0.64–0.82 | higher → more |
| Rain, 7 days before | 882 | 35 | 0.69 | 0.60–0.78 | higher → more |
| Trenton flow (cfs) | 882 | 35 | 0.68 | 0.56–0.78 | higher → more |
| Trenton flow ÷ day-of-year p80 | 882 | 35 | 0.67 | 0.56–0.77 | higher → more |
| Rain, 48h before | 882 | 35 | 0.66 | 0.56–0.76 | higher → more |
| Previous sample's water temp | 881 | 35 | 0.61 | 0.52–0.69 | lower → more |
| Rain, 24h before sample | 882 | 35 | 0.59 | 0.49–0.69 | higher → more |
| Rain noted by DEQ sampler | 882 | 35 | 0.56 | 0.49–0.64 | higher → more |
| Previous sample's salinity | 881 | 35 | 0.52 | 0.42–0.62 | lower → more |
| Previous sample's MPN | 881 | 35 | 0.51 | 0.41–0.61 | lower → more |

## 6. Exceedances by month

| Month | Samples | Exceedances | Rate |
|---|---|---|---|
| 1 | 46 | 6 | 13.0% |
| 2 | 44 | 1 | 2.3% |
| 3 | 47 | 2 | 4.3% |
| 4 | 88 | 2 | 2.3% |
| 5 | 97 | 1 | 1.0% |
| 6 | 97 | 6 | 6.2% |
| 7 | 95 | 1 | 1.1% |
| 8 | 92 | 0 | 0.0% |
| 9 | 85 | 2 | 2.4% |
| 10 | 97 | 4 | 4.1% |
| 11 | 46 | 4 | 8.7% |
| 12 | 48 | 6 | 12.5% |

## 7. Every exceedance, and what the dashboard would have said

4 of 35 exceedances followed less than 0.25" of rain over the prior 7 days — out of reach for any rain-based rule; other causes (e.g. sewage spills) would have to explain those.

| Sampled | Site | MPN | Rain 24h | Rain 72h | Rain 7d | Flow ÷ p80 | Penalty | Rating shown |
|---|---|---|---|---|---|---|---|---|
| 2003-04-08 | C100A | 124 | 0.36" | 0.54" | 0.54" | 0.42 | 0 | Excellent |
| 2003-12-16 | C99 | 111 | 0.00" | 1.68" | 4.18" | 4.34 | -18 | Good |
| 2003-12-16 | C100A | 531 | 0.00" | 1.68" | 4.18" | 4.34 | -18 | Good |
| 2004-03-16 | C100A | 1652 | 1.17" | 1.20" | 1.36" | 0.21 | -28 | Caution |
| 2004-10-20 | C100A | 150 | 0.05" | 0.24" | 1.14" | 1.42 | -10 | Excellent |
| 2004-11-15 | C100A | 124 | 0.00" | 1.14" | 1.14" | 1.75 | -18 | Good |
| 2005-12-21 | C100A | 137 | 0.00" | 0.06" | 2.01" | 1.99 | -10 | Excellent |
| 2006-11-20 | C99 | 164 | 0.00" | 0.00" | 0.74" | 3.88 | -10 | Excellent |
| 2008-09-16 | C100A | 207 | 0.76" | 0.76" | 1.62" | 0.04 | -10 | Excellent |
| 2009-06-24 | C100A | 124 | 0.00" | 0.12" | 0.34" | 0.08 | 0 | Excellent |
| 2009-11-19 | C100A | 111 | 0.96" | 0.97" | 1.28" | 3.56 | -20 | Good |
| 2011-03-22 | C100A | 1298 | 0.00" | 0.00" | 0.16" | 0.15 | 0 | Excellent |
| 2011-05-25 | C100A | 364 | 0.00" | 0.00" | 0.00" | 0.03 | 0 | Excellent |
| 2011-10-12 | C100A | 1013 | 0.19" | 0.23" | 0.24" | 0.31 | 0 | Excellent |
| 2012-06-07 | C100A | 111 | 0.00" | 0.78" | 1.10" | 3.18 | -10 | Excellent |
| 2013-01-07 | C99 | 324 | 0.04" | 0.04" | 0.53" | 1.02 | -10 | Excellent |
| 2013-12-17 | C100A | 192 | 0.00" | 0.64" | 0.88" | 1.05 | -10 | Excellent |
| 2015-10-13 | C100A | 178 | 0.05" | 0.37" | 0.37" | 3.17 | -10 | Excellent |
| 2018-01-31 | C100A | 1298 | 0.00" | 2.36" | 2.37" | 1.20 | -25 | Good |
| 2018-12-17 | C100A | 238 | 0.00" | 1.13" | 1.67" | 4.34 | -18 | Good |
| 2019-01-29 | C100A | 124 | 0.00" | 0.00" | 1.94" | 1.15 | -10 | Excellent |
| 2019-06-11 | C100A | 178 | 1.39" | 1.56" | 2.06" | 0.03 | -28 | Caution |
| 2020-06-17 | C99 | 111 | 0.66" | 2.05" | 4.75" | 4.71 | -35 | Caution |
| 2020-06-17 | C100A | 150 | 0.62" | 2.04" | 4.75" | 4.71 | -35 | Caution |
| 2020-09-16 | C100A | 137 | 0.00" | 0.56" | 0.85" | 1.77 | -10 | Excellent |
| 2020-12-02 | C99 | 137 | 0.00" | 0.90" | 1.13" | 1.05 | -10 | Excellent |
| 2021-01-04 | C100A | 453 | 0.00" | 0.70" | 2.90" | 3.52 | -10 | Excellent |
| 2021-06-15 | C100A | 192 | 0.38" | 0.39" | 3.07" | 1.08 | -10 | Excellent |
| 2022-01-24 | C99 | 137 | 0.00" | 0.41" | 0.54" | 0.51 | 0 | Excellent |
| 2023-01-26 | C100A | 478 | 0.92" | 0.92" | 2.51" | 0.35 | -10 | Excellent |
| 2023-02-14 | C100A | 288 | 0.00" | 1.22" | 1.61" | 0.54 | -8 | Excellent |
| 2024-04-24 | C99 | 111 | 0.00" | 0.34" | 1.04" | 0.30 | 0 | Excellent |
| 2024-07-10 | C99 | 137 | 0.01" | 1.00" | 3.20" | 0.11 | 0 | Excellent |
| 2025-10-30 | C99 | 288 | 0.13" | 0.97" | 0.97" | 0.13 | 0 | Excellent |
| 2025-11-18 | C100A | 124 | 0.00" | 0.00" | 0.00" | 0.06 | 0 | Excellent |
