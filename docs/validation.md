# Validation of the pipeline before the production runs

What was checked on 16 October 2026, before any HPC time was spent, and how to repeat it.
The data servers were not reachable from the test machine, so inputs were synthetic but
physically consistent, laid out exactly like the real sources
(`tests/integration/synthetic.py`, `fake_psl.py`). The HPC setup repeats the RegCM
check on the real 20CRv3 data (`hpc_setup.sh smoke`).

## Model code

| Item | Version |
|---|---|
| RegCM5 | github.com/ICTP/RegCM commit `06a50b5` (15 Oct 2026); built with gfortran 13.3, netCDF-Fortran 4.5.4, MPICH 4.2 and Open MPI |
| WRF namelist keys | checked against the Registry of WRF v4.5 and current master |
| WPS | intermediate reader `util/rd_intermediate.F` compiled from WPS master (6 Jul 2026), big-endian, 4-byte record markers |

## Results

| Check | Result |
|---|---|
| Every namelist key exists in WRF v4.5, WRF master, WPS and RegCM5 sources (`scripts/check_namelists.py`) | pass |
| 20CRv3 downloader on a fake PSL tree (decoy files `tmax.2m`, `rhum`, `pr_wtr.eatm`, `land.sflx`, `cprat` present): picks the right 17 files, 73 three-hourly times 1924-07-12 00 to 07-21 00, levels in Pa, soil layers mapped, static fields | pass |
| ERA5 converter on fake current-CDS files (`valid_time`, `pressure_level`, north-to-south latitude, zipped single-level file): q from dew point, SST filled with skin temperature over land, hourly `tp` to rate | pass |
| WPS intermediate files read by WPS's own `rd_intermediate.exe`: 189 records per time (TT, RH, SPECHUMD, UU, VV on 28 levels + surface; GHT; PSFC, PMSL, SKINTEMP, SST, SEAICE, SNOW, LANDSEA, SOILHGT; ST/SM on 4 layers), correct dates and grid | pass |
| RegCM5 `terrain` on the production 12 km grid: domain 1.82-27.61 N, 60.97-91.25 E (WRF d01: 1.76-27.47 N, 60.91-91.09 E) | pass |
| RegCM5 `sst` and `icbc` read the converted driver through the ERA5 reader at 3-hourly intervals: ps 864-1007 hPa, T 194-302 K, no NaN, correct dates | pass |
| RegCM5 12 km model, 24 h, MOLOCH core, production physics (reduced grid 161 x 141 to fit the test machine) | see below |
| RegCM5 3 km FNEST nested on the 12 km output, 24 h | see below |
| Scoring chain on synthetic WRF output: daily windows, remap, metrics, scorecard, hypotheses, figures (`tests/test_pipeline.py`) | pass |

## Problems found and fixed by these checks

1. **RegCM5 aborts unless the run length is a whole number of days**
   (`Runtime increments must be modulus 24 hours`, `Main/mod_params.F90`). The first
   design ended runs at 06 UTC (198 h and 126 h). Both events now end at 00 UTC
   (216 h and 144 h) for both models, and `tests/test_design.py` enforces it.
2. The installed RegCM5 executable is `regcmMPI`, not `regcm`; `run_regcm.sh` fixed.
3. RegCM5 needs CMIP6 forcing files at run time (historical GHG, ozone for 1900-1949 and
   2000-2014, solar). `get_regcm_static.sh` now fetches exactly those eight files
   (names taken from the RegCM5 source) instead of whole directories.
4. One RegCM5 process holding the full 272 x 242 x 30 grid needs more than 6 GB; this
   is only a constraint on small test machines (the HPC node has 474 GB and runs 20 ranks).
5. The 20CRv3 subsetting now slices in the file's own latitude order before loading, so
   each variable is one small OPeNDAP request.

## Measured cost

RegCM5 MOLOCH at 12 km: about 4.8 microseconds per grid-point-level step per core
(2 cores, 161 x 141 x 30, dt 90 s), inside the 4-8 us bracket used in `docs/budget.md`.
