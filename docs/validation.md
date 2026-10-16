# Validation of the pipeline before the production runs

What was checked on 16 October 2026, before any HPC time was spent, and how to repeat it.
The data servers were not reachable from the test machine, so inputs were synthetic but
physically consistent, laid out exactly like the real sources
(`tests/integration/synthetic.py`, `fake_psl.py`). The HPC setup repeats the RegCM
check on the real 20CRv3 data (`hpc_setup.sh smoke`).

## Model code

| Item | Version |
|---|---|
| RegCM5 | github.com/ICTP/RegCM commit `06a50b5` (15 Oct 2026) plus `patches/regcm5_fnest_z0.patch` and `patches/regcm5_gfortran11_posix.patch`; built with gfortran 13.3 and 11.5, netCDF-Fortran 4.5.4, MPICH 4.2 and Open MPI |
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
| RegCM5 12 km model, 24 h, MOLOCH core, production physics (reduced grid 161 x 141 to fit the test machine) | pass (1465 s on 2 cores) |
| RegCM5 3 km nesting (FNEST) pressure field vs independent hypsometric calculation, after the patch | pass (0.02%) |
| RegCM5 3 km FNEST nested on the 12 km output, 24 h, then output range checks (`check_regcm_output.py`): ps 850-1007 hPa, ta 193-307 K, hus <= 0.019, ua -19..19 m/s, hourly pr <= 15 mm/h | pass (1847 s on 2 cores, 81 x 81 x 50) |
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
6. **RegCM5 nesting (FNEST) opens the coarse ATM file named after the first day of the
   month** (`monfirst` in `PreProc/ICBC/mod_nest.F90`); our 12 km runs start mid-month.
   `scripts/run/regcm_common.sh` links the month-start name to the real file; FNEST then
   picks records by their time values, so the link is exact.
7. **RegCM5 `icbc` can fail and still exit with status 0** (Fortran `STOP`). Success is now
   judged by the files each preprocessor must write (`regcm_check_prep`).
8. **RegCM5 bug at commit 06a50b5**: with explicit convection (3 km) the SHF output
   stream re-enables the convective-precipitation variable `prc` without defining it and
   the model aborts (`NetCDF: Name contains illegal characters`, `mod_ncout.F90` around
   line 1395, where `enable_shf_vars` is overwritten by its own earlier copy). The 3 km
   namelists switch `prc` off with `enable_shf_vars = 8*.true., .false., 2*.true.`;
   total precipitation `pr` is unaffected. Worth reporting upstream.
9. **RegCM5 bug at commit 06a50b5 in MOLOCH-to-MOLOCH nesting**: `init_nest` reverses the
   model-level heights `z0` for interpolation and never restores them, so `writef` builds
   the 3 km pressure column on reversed heights. Without the fix the 3 km ICBC surface
   pressure was 1.50 times the true value, the lowest-level Exner function about 0.4, and the
   3 km model ran to the end with surface pressure collapsing to about 50 hPa (it did not
   crash: only the output check caught it). `patches/regcm5_fnest_z0.patch` (3 lines) fixes
   it; afterwards the nested surface pressure equals an independent hypsometric reduction
   of the 12 km output to the 3 km terrain within 0.02% and the Exner profile matches the
   12 km reference. `hpc_setup.sh` applies the patch before building.
10. **RegCM5 at commit 06a50b5 does not compile with gfortran 11** (found on the HPC,
    gfortran 11.4): `Share/mod_posix.F90` declares the C `opendir` argument as
    `character(len=*, kind=c_char)` inside a `BIND(C)` interface, which gfortran 11 rejects
    (`Character argument 'a' ... must be length 1 because procedure 'opendir' is BIND(C)`);
    gfortran 12 and later accept it. `patches/regcm5_gfortran11_posix.patch` declares it as
    the interoperable `character(kind=c_char), dimension(*)`; the only caller already passes
    a null-terminated string, so the call is unchanged. Checked by reproducing the error
    with gfortran 11.5, building all of RegCM with the patch (0 errors), and running
    `terrain`, `sst` and `icbc` on the E2 12 km case with both compilers: the initial and
    boundary file is bit-identical in ps, T and q, and wind differs by at most 5e-7 m/s.
11. **clima-dods.ictp.it refuses the HPC node** (HTTP 403 for every file, plain curl and
    directory listing alike) while serving the same files to an ordinary connection. The
    11 static files (2.6 GB: GMTED 235 MB, GLCC 22 MB, GLZB 3 MB, GHG 5 x 4-20 MB, ozone
    1.7 GB + 514 MB, solar 61 MB) were fetched on a laptop with
    `scripts/download/get_regcm_static_windows.ps1` and copied with `scp`.

## Measured cost

RegCM5 MOLOCH at 12 km: about 4.8 microseconds per grid-point-level step per core
(2 cores, 161 x 141 x 30, dt 90 s), inside the 4-8 us bracket used in `docs/budget.md`.
