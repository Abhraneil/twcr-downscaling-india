# Scoring

Everything here is computed by `scripts/scoring/score_all.py` from
`config/experiment.yaml`. The criteria in the last section were fixed on
16 October 2026, before any simulation was run, and are not changed after results exist.

## Reference and grid

- **Observations:** IMD 0.25 deg gridded daily rainfall (Pai et al. 2014), land only.
- **Common grid:** the IMD grid. Model and driver rainfall are remapped onto it with an
  area-weighted (first-order conservative) sub-sampling remap (`scripts/postprocess/remap.py`,
  tested for conservation in `tests/test_scoring.py`). Nothing is interpolated onto the
  model grid, so every run is scored on identical cells.
- **Cells scored:** IMD cells with data on every scored day, inside the event's scoring box.
- **Daily windows:** 24 h blocks from 03 UTC (08:30 IST, the IMD observation time).
  WRF: differences of accumulated `RAINC + RAINNC (+RAINSH)` at the window edges.
  RegCM5: sum of hourly mean `pr` from the SHF file. ERA5: hourly `tp`. 20CRv3:
  3-hourly `prate`, taken as the mean over the 3 h ending at the time stamp.
- **IMD date label.** Which window a date label covers is not assumed:
  `scripts/scoring/check_imd_convention.py` reads it off the data (the 944 mm Mumbai
  record fell on 26 July IST and was reported on the morning of 27 July) and fails if
  `observations.imd_label` in the config disagrees.

## Metrics

| Metric | What it answers | Perfect |
|---|---|---|
| `bias_pct` | area-mean event rainfall, model vs IMD (%) | 0 |
| `corr_total` | spatial pattern of the event total (area-weighted, centred) | 1 |
| `rmse_total_mm` | event-total error | 0 |
| `peak_ratio` | largest daily cell value, model / IMD | 1 |
| `q99_ratio` | 99th percentile of daily cell values, model / IMD | 1 |
| `maxloc_err_km` | distance between the event-total maxima | 0 |
| `SAL_S`, `SAL_A`, `SAL_L` | structure, amplitude, location of the event-total field (Wernli et al. 2008; objects above R95/15) | 0 |
| `FSS_<thr>mm_<n>pt` | fractions skill score pooled over the scored days (Roberts and Lean 2008) at 64.5, 115.6 and 204.5 mm/day (IMD heavy, very heavy, extremely heavy) and 1, 3, 5, 9 grid points (0.25, 0.75, 1.25, 2.25 deg) | 1 |
| `AV_*` | added value: model score minus the score of its own driver's rainfall on the same cells (positive = the downscaling helped) | > 0 |

The FSS "useful" level for each threshold is 0.5 + f0/2, with f0 the observed
fraction of cells above the threshold (Roberts and Lean 2008); it is printed by the
scoring script for each event.

## Headline scorecard

`results/SCORECARD.md` shows, for every run: `bias_pct`, `corr_total`, `peak_ratio`,
`maxloc_err_km`, `SAL_S/A/L`, `FSS_115.6mm_5pt`, `FSS_204.5mm_5pt` and
`AV_FSS_115.6mm_5pt`. All other numbers are in `results/scores.csv`.

## Pre-registered criteria

Each is a yes/no statement per case; with two events there is no significance testing.

| ID | Statement | Test |
|---|---|---|
| H1 | The models can produce the event when the driver is good. | E2, ERA5-driven, 3 km: `FSS_115.6mm_5pt` at or above the useful level and abs(`bias_pct`) <= 30, for at least one model |
| H2 | The historical driver costs little. | E2, same model and resolution: `FSS_115.6mm_5pt`(ERA5) - `FSS_115.6mm_5pt`(20CRv3) <= 0.15 and abs(`bias_pct`) <= 30 with 20CRv3 |
| H3 | Downscaling adds value over the driver. | every model run, both events: `AV_FSS_64.5mm_5pt` > 0 |
| H4 | 3 km beats 12 km on extremes. | each model, each case: 3 km closer to 1 than 12 km on `peak_ratio`, and higher `FSS_115.6mm_5pt` |
| H5 | The pre-1950 event is reproduced. | E1, 20CRv3, 3 km: `FSS_64.5mm_9pt` at or above the useful level and abs(`bias_pct`) <= 40, for at least one model |

WRF against RegCM5 is reported side by side without a hypothesis.

## References

- Roberts and Lean 2008, Mon. Wea. Rev. 136:78-97
- Wernli, Paulat, Hagen and Frei 2008, Mon. Wea. Rev. 136:4470-4487
- Wernli, Hofmann, Zimmer 2009, Wea. Forecasting 24:1472-1484
- Pai et al. 2014, MAUSAM 65:1-18
