# Downscaling 20CRv3 over India: two extreme monsoon rainfall events, WRF and RegCM5

Can regional models driven by the **NOAA-CIRES-DOE 20th Century Reanalysis v3** reproduce
extreme west-coast monsoon rainfall, before 1950 as well as today?

| | E1: Kerala, July 1924 | E2: Mumbai, 26 July 2005 |
|---|---|---|
| Era | pre-1950 (only 20CRv3 exists) | 1981-2015 (20CRv3 and ERA5) |
| Drivers | 20CRv3 | 20CRv3, ERA5 (control) |
| Models | WRF 4.5, RegCM5 | WRF 4.5, RegCM5 |
| Resolutions | 12 km and 3 km | 12 km and 3 km |
| Scored against | IMD 0.25 deg daily rainfall, 7 days | IMD 0.25 deg daily rainfall, 4 days |

Nine model runs in total. Every run is scored on the same IMD cells with the same
metrics, against criteria written down before any run (`docs/metrics.md`).

## Status

| Step | State |
|---|---|
| Design, domains, namelists, scoring code | done; namelist keys checked against WRF v4.5 / master and RegCM5 sources |
| Pipeline validation | RegCM5 built and run on converted driver files; WPS reader accepts the intermediate files (`docs/validation.md`) |
| Data download and setup | `scripts/setup/hpc_setup.sh` (overnight, 16 Oct) |
| Model runs | `scripts/run/launch_all.sh` (17 Oct), progress with `scripts/run/status.sh` |
| Scores and figures | to do: `results/` fills from `scripts/scoring/score_all.py` |

## Repository

```
config/experiment.yaml        single source of truth: domains, dates, boxes, thresholds
namelists/                    generated from the config (never edited by hand)
  wps/ wrf/ regcm/            one per event x driver (x resolution for RegCM)
  GEOMETRY.md                 domain corners and nest indices
scripts/
  generate_namelists.py       config -> namelists
  check_namelists.py          every namelist key checked against the model source code
  budget.py                   compute + storage budget -> docs/budget.md
  download/                   20CRv3 (PSL OPeNDAP), ERA5 (CDS), IMD, RegCM static data
  preprocess/                 driver -> WPS intermediate files, driver -> RegCM ERA5-format files
  run/                        run_wps.sh, run_wrf.sh, run_regcm.sh, run_all.sh, env.sh
  postprocess/                daily rainfall on the IMD grid (conservative remap)
  scoring/                    metrics, scorecard, pre-registered criteria, figures
tests/                        unit tests + an end-to-end test on synthetic WRF output
docs/                         design, metrics, budget, model availability, runbook, write-up outline
results/                      scores.csv, SCORECARD.md, HYPOTHESES.md, figures/ (after the runs)
```

## Reproduce

```bash
conda env create -f environment.yml && conda activate twcr
pytest -q                                     # checks the code before any run
bash scripts/setup/hpc_setup.sh               # build RegCM5, download data, checks, smoke test, WPS
bash scripts/run/launch_all.sh                # nine runs in four lanes on one 64-core node
bash scripts/run/status.sh                    # progress
```

Step-by-step commands, the schedule and failure handling are in `docs/runbook.md`.

## Key choices

- **Events are rainfall, not humid heat.** Gridded observations exist for 1924 rainfall
  (IMD from 1901) but not for 1924 temperature or humidity, so only rainfall can be
  verified on a grid in both eras.
- **ERA5 control in 2005** separates model error from driver error.
- **12 km and 3 km.** 12 km is the CORDEX-CORE scale with parameterised convection;
  3 km is convection-permitting. One shared 12 km domain; one 3 km domain per event.
- **Both drivers go through one code path per model**: Python writes WPS intermediate
  files (no ungrib) and RegCM5 ERA5-format files (RegCM5 has no 20CRv3 reader).
- **No interior nudging** in either model, so the comparison is fair and the drivers
  only act through the boundaries.
- **COSMO-CLM is not included**: its source is members-only and cannot go in a public
  repository (`docs/model_availability.md`).

## Budget

15-29 node-hours on one 64-core node for all nine runs, about 205 GB of raw output,
under 1 GB of inputs needed to reproduce. Details and storage costs: `docs/budget.md`.

## Data and credits

20CRv3: Support for the Twentieth Century Reanalysis Project version 3 dataset is
provided by the U.S. Department of Energy, Office of Science Biological and Environmental
Research (BER), by the National Oceanic and Atmospheric Administration Climate Program
Office, and by the NOAA Physical Sciences Laboratory. ERA5: Copernicus Climate Change
Service. Rainfall: India Meteorological Department (Pai et al. 2014). Models: WRF (NCAR),
RegCM5 (ICTP).

## Licence

Code: MIT (see `LICENSE`). Documentation and results: CC BY 4.0.
