# Multi-event study: the pipeline

Twenty Indian extreme-rainfall events (1901-2015) plus two anchors (Kerala 1924, Mumbai 2005),
WRF 4.5 at 36/12 km, driven by 20CRv3 (all events) and ERA5 (events from 1940), physics sets
P0-P6. Design, selection rule and criteria: [`docs/multievent/design.md`](../docs/multievent/design.md).
Settings: [`study.yaml`](study.yaml). Every step is a numbered script, run from the repository root.

```bash
cp multievent/site.env.example multievent/site.env      # edit: ME_ROOT, toolchain, scheduler
```

| Step | Script | What it does | Time |
|---|---|---|---|
| **Installation** | | | |
| 1 | `01_install_libraries.sh` | checks gcc/gfortran/csh; uses the system's MPI and netCDF or builds MPICH / zlib / HDF5 / netCDF into `$ME_ROOT/prefix`; makes `$ME_ROOT/prefix/netcdf` for WRF | 1 min, or 1 h if it builds |
| 2 | `02_install_wrf_wps.sh` | WRF 4.5 + Thompson fix (`patches/wrf45_thompson_fix.py`), dmpar; WPS 4.5 serial, no GRIB2. Or checks the existing builds named in site.env | 30-90 min |
| 3 | `03_install_python.sh` | `$ME_ROOT/venv` (conda or venv + pip), runs the tests | 5 min |
| 4 | `04_check_installation.sh` | builds, Thompson fix, every WPS geography data set GEOGRID.TBL asks for, MPI, Python, scheduler, disk, data servers | 1 min |
| **Data** | | | |
| 5 | `05_download_imd.sh` | IMD 0.25 deg rain 1901-2015 | 30-60 min |
| 6 | `06_select_events.sh` | the 20 events by the fixed rule -> `results/multievent/`, `multievent/events.yaml` (then document and commit them) | 5 min |
| 7 | `07_download_20crv3.sh` | 20CRv3 subsets per event (PSL OPeNDAP) | 10-30 min per event |
| 8 | `08_download_era5.sh` | ERA5 per event from 1940 (CDS; ~/.cdsapirc) | hours (CDS queue) |
| **Cases** | | | |
| 9 | `09_create_cases.sh` | one case per event x driver x physics set: `case.json`, namelists, iofields; `runs/cases.csv`. Checks everything before writing anything | seconds |
| 10 | `10_run_wps.sh` | geogrid per event, intermediate files (Python), metgrid per event x driver; marks finished work with a hash of its namelist | 5-15 min per pair |
| **Running** | | | |
| 11 | `11_run_cases.sh` | real.exe + wrf.exe per case: local lanes, or one PBS/SLURM job per case; restarts every 12 h, resumes after a stop | 2-6 h per case on 16 cores |
| 12 | `12_status.sh` | state, model time and progress of every case | seconds |
| 13 | `13_extract_rain.sh` | daily rain of each finished case and its driver on the IMD grid | 1 min per case |
| 14 | `14_cleanup.sh` | removes the met_em files of an event x driver once every case of the pair has finished | seconds |

Scoring against the criteria (M1-M6) is added once the criteria are fixed in a commit
(design.md, section 6), before the first run.

## Where things go

`$ME_ROOT` (site.env): `prefix/` and `build/` (libraries, WRF, WPS), `venv/`, `data/obs` (IMD),
`data/drivers` (20CRv3, ERA5), `data/daily` (rain on the IMD grid), `runs/wps/<event>/<driver>`,
`runs/cases/<event>_<driver>_<P>`, `logs/`. Each case directory keeps `case.json` with every
resolved setting; `09_create_cases.sh` refuses to change a case that exists. With `--force` it
moves the old case directory, outputs included, to `runs/cases/_superseded/` and creates it anew;
a change of an event's WPS settings must take all cases of that event x driver along.

## Running safely

- **One run per case.** A case runs under the lock `<case>/.run.lock` (host, pid, refreshed every
  5 min). A second start, from another lane, job or machine, exits without touching it. A lock
  whose owner died, or that has not been refreshed for 30 min, is taken over.
- **Stops are resumed.** Every unsuccessful exit (crash, walltime, node failure, `kill`) writes
  `failed.txt` with the reason; step 11 continues such a case from its last usable restart files.
  A wrf.exe silent for 90 min is stopped and resumed. Two stops at the same model time from the
  same restart end the case (a model problem).
- **Queued jobs are not submitted twice.** If `qstat`/`squeue` does not answer, a case with a job
  counts as queued.
- **Start again from real.exe:** `FRESH=1 bash multievent/11_run_cases.sh --cases <case>` (also
  for finished cases; their output is replaced). A requeued job continues instead of starting over.
- **Restarts use the settings the case was created with.** The namelist is written from
  `case.json`, and only while the code still writes the namelist the case was created with
  (`namelist.input.template`); otherwise the case must be recreated (`--force`).
- **met_em files belong to their WPS settings.** real.exe refuses met_em files whose `.wps_ok`
  does not match the current `namelist.wps.template`; a continuation does not need them.

Disk, for 22 events x their drivers x 7 physics sets (about 230 runs): about 140 GB for the P0 runs
(hourly 12 km rain and 2-D fields, 3-hourly 3-D fields), 90 GB for P1-P6 (3-hourly 2-D), 60 GB
for the 36 km domain, plus up to 5 GB of met_em per event x driver until `14_cleanup.sh`.

## Two machines

- **gpu-h100** (PBS, one 64-core node, internet): set `ME_ENV_SCRIPT=$HOME/WRFCHEM/scripts/env_wrfchem.sh`,
  `ME_WRF_DIR=$HOME/TWCR/WRF-4.5-thompsonfix` and the existing WPS in site.env; step 2 then only
  checks them. `ME_SCHEDULER=local`, `ME_LANES=4`, `ME_NPROCS=16`. Downloads (steps 5-8) run here.
- **Second HPC** (8 nodes x 16 cores): steps 1-4 there; `ME_SCHEDULER=pbs` or `slurm`,
  `ME_NPROCS=16`. UCAR downloads are blocked on both machines: copy the WPS geography from
  gpu-h100 (`rsync -a ~/WRFCHEM/WPS_GEOG/ <second-hpc>:<ME_WPS_GEOG>/`), and copy
  `$ME_ROOT/data` if that machine cannot reach PSL, CDS or IMD.

All steps are idempotent: run a step again and it continues where it stopped.

## Tests

Steps 1-2 were run on a clean Ubuntu 24.04 machine (GCC 13.3, the system's Open MPI and netCDF,
2 cores): WRF 4.5 dmpar with the Thompson fix (configure option 34; WRF's netCDF-4 link test
failed there, so it fell back to classic netCDF) built in 21 min, WPS 4.5 (option 2) in 1 min.

`tests/test_multievent.py` checks the geometry, dates and namelists, and runs steps 9-14 end to
end with stand-in WRF/WPS executables (`tests/integration/fake_wrf`): a stop that fails the case,
its continuation from the restart files after the met_em files are gone, a second start refused
by the lock, a dead owner's lock taken over, `--force`, a scheduler that does not answer, and an
anchor that the selection rule picks anyway. With a WRF source tree, `WRF_SRC=<path> pytest tests/test_multievent.py`
also checks every namelist key against the WRF Registry.
