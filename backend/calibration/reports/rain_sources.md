# Rain source: KEWN gauge vs radar at the sampling site

450 samples (2014–2026) with confirmed KEWN rain and radar coverage; 18 exceedances. Same model and features throughout — only the rain source changes. Leave-one-year-out.

| Rain source | AUC | AUC 95% CI | Brier skill | Log loss |
|---|---|---|---|---|
| Base rate only | 0.50 | — | +0.0% | 0.1705 |
| Deployed: KEWN hourly, to sample time | 0.78 | 0.67–0.88 | +9.2% | 0.1461 |
| KEWN gauge (daily) | 0.74 | 0.63–0.85 | +6.8% | 0.1516 |
| MRMS radar at site | 0.72 | 0.59–0.85 | +6.0% | 0.1542 |
| Stage IV radar at site | 0.73 | 0.60–0.85 | +5.6% | 0.1533 |

## Head to head vs KEWN (same daily windows, same days)

- **MRMS radar at site**: AUC 0.72 vs 0.74 (difference 95% CI -0.06 to +0.02); Brier difference 95% CI -0.0010 to +0.0018 (negative favors radar)

- **Stage IV radar at site**: AUC 0.73 vs 0.74 (difference 95% CI -0.04 to +0.01); Brier difference 95% CI -0.0010 to +0.0023 (negative favors radar)


## How closely the sources agree (3-day rain, correlation)

|  | kewn_d1_3 | mrms_d1_3 | stage4_d1_3 |
|---|---|---|---|
| kewn_d1_3 | 1.0 | 0.87 | 0.9 |
| mrms_d1_3 | 0.87 | 1.0 | 0.92 |
| stage4_d1_3 | 0.9 | 0.92 | 1.0 |
