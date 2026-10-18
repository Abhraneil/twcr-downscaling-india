# Write-up outline (due 26 October 2026)

Target: 6-8 pages, figures from `results/figures/`, numbers only from `results/scores.csv`.
Results order, figure captions and the numbers to quote: `docs/story.md`.

1. **Summary** (150 words): question, two events, two models, two resolutions, the
   H1-H5 outcome in one sentence each.
2. **Why 20CRv3**: only 3-D reanalysis before 1940; surface-pressure-only assimilation;
   what that means for moisture and rain (Slivinski et al. 2019, 2021).
3. **Prior work**: Stucki et al. 2020 (WRF from 20CR, Alpine floods, ensemble mean as
   minimum-error choice); 1816 WRF + DA study; Kong and Bi 2015 (centennial WRF from 20CR,
   China); CCLM downscaling of 20CR for Central European floods. Gap: none over India,
   none comparing two regional models.
4. **Design**: `docs/experiment_design.md` condensed: events and why rainfall, drivers,
   resolutions, model configurations table, run matrix.
5. **Verification method**: IMD grid, remap, 03 UTC windows and the label check, metric
   table, pre-registered criteria (`docs/metrics.md`).
6. **Results**
   - E2 with ERA5: can the models do it at all (H1); maps and FSS curves
   - E2 20CRv3 vs ERA5: the driver penalty (H2)
   - Added value over the drivers (H3); 12 vs 3 km (H4)
   - E1 1924 (H5); comparison with the documented flood timing (peak 16-17 July at Aluva)
   - WRF vs RegCM5 side by side
7. **Limitations**: two cases; ensemble mean only; present-day land use in 1924; sparse
   1924 gauges; different soil initialisation between models.
8. **Next steps**: 20CRv3 members for E1 (spread of downscaled rain); more pre-1950
   events from the IMD record; humid heatwaves with station wet-bulb; ICON-CLM as a
   third, open model.
9. **Reproducibility**: repository tag, Zenodo DOI, compute used (from `timing.txt`).
