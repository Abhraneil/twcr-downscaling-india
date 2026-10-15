# Runbook and schedule

Deadlines: **repository public on Saturday 24 October 2026**, **write-up on Monday 26 October**.
The whole run matrix needs 13-26 node-hours on one 64-core node (`docs/budget.md`),
so compute is not the constraint; data access, the RegCM5 build and reruns are.

## Schedule

| Day | Work | Done when |
|---|---|---|
| Fri 16 Oct | Push this repository (private). Build RegCM5 on the HPC. Start downloads: IMD, 20CRv3 (both events), ERA5 (CDS queue can take hours), RegCM static data. | `check_imd_convention.py` passes; three files in `data/drivers/` |
| Sat 17 Oct | WPS for the three driver cases. **1-day WRF benchmark** (step 5), update `COST_*` in `scripts/budget.py`. Launch WRF E2-ERA5. | E2-ERA5 `wrf.exe` SUCCESS |
| Sun 18 Oct | WRF E2-20CRv3 and E1-20CRv3. RegCM5 12 km for all three cases. | 3 WRF + 3 RegCM 12 km complete |
| Mon 19 Oct | RegCM5 3 km for all three cases. | 9 of 9 runs complete |
| Tue 20 Oct | Extract, score, plot. Sanity checks (step 8). | `results/SCORECARD.md`, `HYPOTHESES.md` |
| Wed 21 Oct | Buffer for reruns (CFL, RegCM boundary issues). | |
| Thu 22 Oct | Freeze results. Upload daily fields + inputs needed to reproduce to Zenodo (DOI). | DOI in README |
| Fri 23 Oct | README results section, CI green, tag `v1.0`. | |
| Sat 24 Oct | Make the repository public. | **deadline** |
| Sun 25 - Mon 26 Oct | Write-up from `docs/writeup_outline.md`. | **deadline** |

## Steps

```bash
# 0. once
git clone <repo> && cd twcr-downscaling-india
conda env create -f environment.yml && conda activate twcr
$EDITOR scripts/run/env.sh              # WPS_DIR, WRF_DIR, REGCM_BIN, RCMDATA, RUN_ROOT
source scripts/run/env.sh
echo "url: https://cds.climate.copernicus.eu/api
key: <your-key>" > ~/.cdsapirc

# 1. RegCM5 build (MPI + netCDF; MPICH as on the node)
git clone https://github.com/ICTP/RegCM.git $HOME/RegCM && cd $HOME/RegCM
./bootstrap.sh && ./configure && make -j 16 && make install     # installs into $HOME/RegCM/bin
cd -

# 2. observations and drivers
python scripts/download/get_imd.py 1924 2005
python scripts/scoring/check_imd_convention.py           # must exit 0
python scripts/download/get_20crv3.py E1_kerala1924
python scripts/download/get_20crv3.py E2_mumbai2005
python scripts/download/get_era5.py   E2_mumbai2005
bash   scripts/download/get_regcm_static.sh

# 3. WPS (geogrid, intermediate files checked with rd_intermediate.exe, metgrid)
bash scripts/run/run_wps.sh E2_mumbai2005 ERA5

# 4. WRF
bash scripts/run/run_wrf.sh E2_mumbai2005 ERA5

# 5. benchmark first: run 24 h only, read timing.txt, put the measured
#    core-seconds per point-level-step into scripts/budget.py and re-run it
#    (edit run_hours = 24 in the run directory's namelist.input for this one test)

# 6. RegCM5 (12 km from the reanalysis, then 3 km nested)
bash scripts/run/run_regcm.sh E2_mumbai2005 ERA5 both

# 7. repeat 3, 4, 6 for E2_mumbai2005 20CRv3 and E1_kerala1924 20CRv3
#    (or run everything: bash scripts/run/run_all.sh)

# 8. scoring
python scripts/postprocess/extract_precip.py E1_kerala1924 --runs-root $RUN_ROOT
python scripts/postprocess/extract_precip.py E2_mumbai2005 --runs-root $RUN_ROOT
python scripts/scoring/score_all.py
python scripts/scoring/plot_event.py
```

## Sanity checks before trusting a score (step 8)

1. The driver files pass `check_standard` (the download scripts call it): ranges, units,
   regular grid, Pa levels.
2. `rd_intermediate.exe` reads the first intermediate file (`run_wps.sh` stops otherwise).
3. 12 km MSLP at the event peak looks like the driver's (no drift without nudging);
   compare `wrfout_d01` / RegCM ATM `psl` with the driver PMSL in ncview.
4. Driver rainfall (`DRIVER_*`) totals are of the right order compared with IMD; a
   driver baseline off by a factor of 3 or 8 means a time-window or unit error.
5. `pytest -q` passes.

## Known failure modes

- **WRF CFL errors** (`cfl` in `rsl.error.*`, NaN): in `scripts/generate_namelists.py`
  change `time_step` from `5 * dx` to `4 * dx` (48 s), regenerate the namelists, rerun.
- **RegCM5 MOLOCH instability at 3 km**: lower `dt` from 30 to 24 s in
  `generate_namelists.py`, regenerate, rerun.
- **OPeNDAP timeouts at PSL**: the script retries four times; if it still fails, download
  the whole yearly files from the THREDDS `fileServer` URL printed in the error and
  point `open_remote` at the local copies (about 36 GB per year).
- **CDS queue**: submit the ERA5 request first thing; it is the slowest download.

Every change to physics or time step goes through `config/experiment.yaml` or
`scripts/generate_namelists.py`, never by editing a namelist in a run directory, so the
repository always holds what was actually run.
