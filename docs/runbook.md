# Runbook

Deadlines: repository public **Saturday 24 October 2026**, write-up **Monday 26 October**.

## Tonight (Friday 16 October): setup, downloads, smoke test, WPS

```bash
# 1. copy the repository to the HPC and unpack it
mkdir -p ~/TWCR && cd ~/TWCR
#    (from your laptop)  scp twcr-downscaling-india.tar.gz <you>@<hpc>:~/TWCR/
tar xzf twcr-downscaling-india.tar.gz && cd twcr-downscaling-india

# 2. run the overnight setup inside tmux so it survives a dropped connection
tmux new -s twcr
bash scripts/setup/hpc_setup.sh 2>&1 | tee ~/TWCR/setup.log
#    detach: Ctrl-b d      re-attach: tmux attach -t twcr
```

What `hpc_setup.sh` does, in order (each stage can be re-run by name, e.g.
`bash scripts/setup/hpc_setup.sh download check`):

| Stage | What | Time |
|---|---|---|
| `detect` | loads `~/WRFCHEM/scripts/env_wrfchem.sh`, finds the plain WRF 4.5 and WPS builds (skips the `-ent` copy), writes `scripts/run/site.env` | 1 min |
| `reach` | which data servers the node can reach; `~/.cdsapirc` present | 1 min |
| `python` | `~/TWCR/venv` (conda if present, else venv) and `pytest` | 5 min |
| `regcm` | clones RegCM5, checks out the tested commit `06a50b5`, builds with the WRF toolchain (MPICH, gfortran, netCDF) | 10 min |
| `download` | ERA5 (CDS queue), 20CRv3 for both events (OPeNDAP subsets), IMD 1924 + 2005, RegCM static data (about 4 GB): all in parallel | 15 min to a few hours (CDS queue) |
| `check` | IMD date convention, every driver file against physical ranges, conversion to WPS intermediate (read back with `rd_intermediate.exe`) and to RegCM input | 5 min |
| `smoke` | RegCM5 12 km + 3 km for 24 h on the real E2 20CRv3 driver, production grids, 32 ranks | 30 min |
| `wps` | geogrid + metgrid for all three cases, so `met_em` files are ready in the morning | 30-60 min |

It ends with `SETUP COMPLETE` or a list of what failed. Logs: `~/TWCR/logs/`.

**If a server is unreachable from the HPC** (`reach` says so):
- psl.noaa.gov: run `python scripts/download/get_20crv3.py <event>` on any machine that
  can reach it (transfers ~50 MB) and copy `data/drivers/<event>_20CRv3*.nc` to the same
  place on the HPC.
- clima-dods.ictp.it: run `scripts/download/get_regcm_static.sh` elsewhere and copy
  `~/TWCR/RCMDATA/` across (about 4 GB).
- imdpune.gov.in: download `Rainfall_ind1924_rfp25.grd` and `Rainfall_ind2005_rfp25.grd`
  from https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html into `data/raw/imd/`.

## Tomorrow (Saturday 17 October): launch all nine runs

```bash
cd ~/TWCR/twcr-downscaling-india
bash scripts/run/launch_all.sh        # four lanes in the background, returns immediately
bash scripts/run/status.sh            # model time reached, % done, ETA for every run
```

| Lane | Ranks | Runs | Estimated wall time |
|---|---|---|---|
| `wrf_E1` | 20 | WRF E1 1924 20CRv3 | 13-25 h |
| `wrf_E2_era5` | 12 | WRF E2 2005 ERA5 | 14-28 h |
| `wrf_E2_20cr` | 12 | WRF E2 2005 20CRv3 | 14-28 h |
| `regcm` | 20 | RegCM5 12+3 km for E2 ERA5, E2 20CRv3, E1 20CRv3 | 13-27 h |

Check `status.sh` 15 minutes after launch: every WRF run should have passed `real.exe`
and be advancing; the RegCM lane should be in the 12 km E2 ERA5 run. Each finished run
writes `timing.txt`; put the measured cost into `COST_LO/COST_HI` in `scripts/budget.py`
for the write-up.

## When the runs finish (Sunday 18 - Tuesday 20 October): score

```bash
source scripts/run/env.sh
for EV in E1_kerala1924 E2_mumbai2005; do
  $PYTHON scripts/postprocess/extract_precip.py $EV --runs-root $RUN_ROOT
done
$PYTHON scripts/scoring/score_all.py        # results/scores.csv, SCORECARD.md, HYPOTHESES.md
$PYTHON scripts/scoring/plot_event.py       # results/figures/
$PYTHON scripts/scoring/story_figures.py --runs-root $RUN_ROOT   # results/figures/story/ (write-up)
```
`score_all.py` first checks the IMD date convention against the data and refuses to score
if `observations.imd_label` disagrees (validation item 23).

## Optional, post hoc: WRF physics sensitivity for E2 (not part of H1-H5)

One extra WRF run of E2 with ERA5, WSM6 + Grell-Devenyi instead of Thompson + Grell-Freitas
(the schemes Kumar et al. 2008 used when they reproduced the Santacruz total). About 30 h on
12 ranks on the shared node, like the baseline. Its output stays out of `data/daily`,
`results/scores.csv` and the hypotheses.

```bash
source scripts/run/env.sh
nohup bash scripts/sensitivity/wsm6gd.sh > $TWCR_HOME/logs/sens_wsm6gd.log 2>&1 &
head -12 $TWCR_HOME/logs/sens_wsm6gd.log     # the namelist diff: exactly mp_physics and cu_physics
bash scripts/run/status.sh                   # listed as "WRF E2_mumbai2005 ERA5 wsm6gd"
# when it has finished:
$PYTHON scripts/sensitivity/score_wsm6gd.py --runs-root $RUN_ROOT   # results/sensitivity/
```

## Remaining schedule

| Day | Work |
|---|---|
| Wed 21 Oct | buffer for reruns |
| Thu 22 Oct | freeze results; daily fields + driver subsets to Zenodo |
| Fri 23 Oct | README results section, CI green, tag `v1.0` |
| Sat 24 Oct | repository public |
| Sun 25 - Mon 26 Oct | write-up (`docs/writeup_outline.md`) |

## Failure handling

Every change to physics or time step goes through `config/experiment.yaml` or
`scripts/generate_namelists.py` and `python scripts/generate_namelists.py`, never by
editing a namelist inside a run directory, so the repository always holds what ran.

| Symptom | Fix |
|---|---|
| WRF `cfl` errors or NaN in `rsl.error.*` | `time_step` from `5 * dx` to `4 * dx` in `generate_namelists.py`, regenerate, rerun that case |
| RegCM 3 km aborts with instability | `dt` from 30 to 24 s for `03km` in `generate_namelists.py`, regenerate, rerun |
| RegCM `Runtime increments must be modulus 24 hours` | run length must be whole days (the config and a test enforce this) |
| `real.exe` complains about missing soil levels | check `num_metgrid_soil_levels = 4` and that the driver file has ST/SM |
| OPeNDAP timeouts at PSL | re-run the download stage (it retries); or use `TWCR_20CR_LOCAL` with whole yearly files (see `get_20crv3.py`) |
| CDS request queued for hours | leave it; `get_era5.py` resumes and skips files already downloaded |

## Disk space: finished output moved off /home

Models write on /home (`~/TWCR/runs`); `scripts/run/offload.sh --loop` moves every file no model
will open again to /Datastorage every 3 h, or at once when /home falls below 40 GB free,
leaving symlinks so scoring reads the usual paths. That covers the output of finished RegCM5
runs, WRF history files before the latest usable restart (WRF writes 12-hour files,
validation item 22), WRF inputs of finished runs and the met_em files once real.exe has run.
/Datastorage is shared and was filling at about 15 GB/h from other users, so the mover never
takes it below 50 GB free (`OFFLOAD_DEST_RESERVE_GB`); files stay on /home instead and the
log says so. Log: `~/TWCR/logs/offload.log`.

On 18 October /home suddenly had about 750 GB free while /Datastorage reached 99%, so the
mover was stopped and everything it had moved was copied back with
`bash scripts/run/offload.sh --bring-back` (copy, compare, replace the symlink, delete the copy
on /Datastorage). From then on all output stays on /home.

(The first WRF attempt ran with its run directory on /Datastorage, before WRF wrote
12-hour files; see validation item 21 for why it was restarted.)

```bash
setsid nohup bash scripts/run/offload.sh --loop > /dev/null 2>&1 < /dev/null &
```
