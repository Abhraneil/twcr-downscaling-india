# Validation of the pipeline before the production runs

What was checked on 16 October 2026, before any HPC time was spent, and how to repeat it.
The data servers were not reachable from the test machine, so inputs were synthetic but
physically consistent, laid out exactly like the real sources
(`tests/integration/synthetic.py`, `fake_psl.py`). The HPC setup repeats the RegCM
check on the real 20CRv3 data (`hpc_setup.sh smoke`).

## Model code

| Item | Version |
|---|---|
| RegCM5 | github.com/ICTP/RegCM commit `06a50b5` (15 Oct 2026) plus `patches/regcm5_fnest_z0.patch` and `patches/regcm5_gfortran11_posix.patch`; built with gfortran 13.3 and 11.5, netCDF-Fortran 4.5.4, MPICH 4.2 and Open MPI 4.1.6; on the HPC with gfortran 11.4 and Open MPI 4.1.6 (`build_openmpi.sh`) |
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
12. **CDS rejects the ERA5 pressure-level request as too large** (`403 ... cost limits
    exceeded`): 5 variables x 37 levels x 7 days x 8 times in one request. `get_era5.py` now
    asks for one variable per request and, if CDS still refuses, halves the day list;
    downloads go to `.part` files first, so an interrupted request never leaves a file that
    looks complete. Tested offline against a fake CDS that rejects requests the same way:
    17 requests, and the driver built from the pieces is identical (difference 0.0) to the
    one built from a single request.
13. **A 20CRv3 OPeNDAP transfer can be cut short without an exception**
    (`ERR: DAP DATADDS packet is apparently too short` for `air.1924`, after which the script
    carried on). Every field is now checked after transfer (no missing values where the
    models need them, physical bounds per variable) and fetched again if it fails, up to 5
    times. `check_standard` also rejects missing values in the fields the models read
    everywhere and checks Z, U, V and SKT bounds. Tested offline by damaging the first two
    transfers of T (zeros, then a missing tail): both were caught, the third was used.
14. **20CRv3 specific humidity has fewer pressure levels than temperature.** On the HPC the
    E2 driver failed `check_standard` with `Q has 520331 missing values` = exactly 7 levels
    x 49 times x 37 x 41 points: after alignment to the 28 T levels, Q had nothing on the 7
    highest. `get_20crv3.py` now logs the native levels of every 3-D field and holds q at its
    top published value above that (stratospheric q is a few 1e-6 kg/kg); a gap anywhere
    else, or in T, Z, U or V, stops the download. `tests/integration/fake_psl.py` now writes
    shum on 21 levels (1000-100 hPa) to reproduce this; the driver, the WPS intermediate
    files and the RegCM input are then complete.
15. **PSL repeatedly cuts short large OPeNDAP responses for 1924.** On the HPC the E1 download
    got T all zeros, Z up to 1e33, and V with the same 9,303 missing values on consecutive
    retries: repeating the same request does not help. After two failed whole-field reads,
    `get_20crv3.py` now requests one day (8 time steps) at a time, checks and retries each
    piece, and if a piece still fails reports which times and levels are missing, so a
    broken transfer can be told apart from a gap in the data. Tested offline: a whole-field
    read that always loses 9,303 values is recovered from 10 daily pieces; a real gap (one
    time, one level) stops the download with `missing at time 1924-07-15T06; level 925`.
16. **ERA5 specific humidity has small negative values** (min -6.8e-6 kg/kg in the E2 box),
    which failed the -1e-6 bound in `check_standard`. `get_era5.py` sets negative q to zero and
    logs how many; a minimum below -1e-4 kg/kg still stops it.
17. **RegCM5 aborts at start-up on the HPC: `MPI_Scatterv ... Negative count`** (12 km, 32
    ranks). The same grid and rank count (8 x 4) run correctly here with Open MPI, so the
    decomposition is fine. `tests/integration/mpi_f08_check.f90` repeats RegCM5's own
    gather-then-scatter through `mpi_f08`: with the HPC's MPICH 4.0.3 + gfortran 11.4 the
    gathered windows were wrong on 4 of 4 and 32 of 32 ranks. WRF uses the older `mpi`
    interface and is unaffected. `scripts/setup/build_openmpi.sh` builds Open MPI 4.1.6 with
    the same gfortran, runs the check (must print `MPI f08 OK` at 4 and 32 ranks), rebuilds
    RegCM5 against it and verifies it links `libmpi_usempif08.so.40` and no MPICH library;
    `env.sh` then launches RegCM5 with that Open MPI (`--bind-to none`, so the concurrent
    WRF lanes are not pinned to the same cores) while WRF and WPS keep MPICH.
18. **RegCM5 rebuilt with Open MPI still loaded MPICH** (`build_openmpi.sh` stopped on its
    linkage check). The netCDF 4.9.0 and HDF5 in `~/WRFCHEM/libraries` were built with MPICH's
    `mpicc`/`mpifort` (parallel I/O), so `libnetcdff`, `libnetcdf`, `libhdf5` and `libhdf5_hl`
    each pull in `libmpi.so.12`; RegCM5's configure also takes `nc-config`/`nf-config` from
    PATH. `scripts/setup/build_netcdf_serial.sh` builds HDF5 1.14.6, netCDF-C 4.9.2 and
    netCDF-Fortran (serial, static, plain gcc/gfortran) in `$TWCR_HOME/netcdf-serial` and
    rebuilds RegCM5 with them and Open MPI (on the HPC, downloads.unidata.ucar.edu failed
    certificate verification, so the identical upstream tarballs came from the Ubuntu archive:
    netCDF-C 4.9.2 and netCDF-Fortran 4.5.4); it stops unless `terrain`, `sst`, `icbc` and
    `regcmMPI` link no shared MPICH, netCDF or HDF5 library. Static linking leaves PATH and
    LD_LIBRARY_PATH unchanged, so WRF and WPS are not affected. Checked here end to end:
    the rebuilt preprocessors write netCDF-4 files and the 12 km model starts on 8 ranks with
    the same surface-pressure range (862.76-1006.49 hPa) as the earlier build.
19. **real.exe stopped at once with `ERROR reading namelist namelist_quilt`** (all three WRF
    cases). WRF 4.5 reads `&namelist_quilt` itself (frame/module_io_quilt_old.F, `READ(...,
    IOSTAT=io_status)` then `wrf_error_fatal` on any non-zero status), so the group is
    mandatory even without I/O quilting; the other groups fall back to Registry defaults.
    The generated namelists now carry `&grib2` and `&namelist_quilt` (`nio_tasks_per_group =
    0`, `nio_groups = 1`), and `scripts/check_namelists.py` also reads the NAMELIST
    declarations in WRF's frame/ sources and fails if a required group is missing (it flags
    the old namelists and passes the new ones).
20. **WRF E2 ERA5 had 257 land points with soil water <= 0.01 m3/m3** (minimum 0.002) in its
    12 km `wrfinput`, created by item 16's setting of small negative ERA5 values to zero at
    coastal land points; the 20CRv3 inputs have none (minimum 0.053). Completely dry soil is
    unphysical in the monsoon. `get_era5.py` now fills land values below 0.01 m3/m3 from the
    nearest valid land point (same layer and time); sea points are left alone. On the HPC the
    fill touched 65,981 land values (all layers and times): the 15,193 zeroed negatives plus
    small positive values below 0.01, some of them genuinely dry desert soil (Balochistan,
    Thar) now raised to the nearest value of at least 0.01, a negligible change far from the
    E2 scoring box. RegCM5 does not read driver soil moisture, so its ERA5 runs are unaffected.
    This was first taken for the cause of the crash in item 21 (the run had stopped in
    microphysics after 8 h 19 min); it was not: the rerun with filled soil crashed at 9 h 03 min.

21. **All three WRF runs crashed in Thompson microphysics: an out-of-bounds table read in WRF
    4.5.** E1 1924 at 117.6 h, E2 20CRv3 at 74 h, E2 ERA5 at 8.3 h and (after item 20) 9.05 h:
    segmentation faults in `mp_thompson` with no CFL warning in any run, on 12 and 20 ranks,
    for both events and both drivers. The node was not short of memory (at least 250 GB
    available throughout, `sar -r`; no OOM events). All three crashes are at the same machine
    instruction (`mp_thompson+0xc1dc`, a double-precision `minsd` with its operand read from
    memory; `scripts/diagnostics/faultpc.py`), i.e. one source line.
    The cause is in `phys/module_mp_thompson.F`. Without hail-aware graupel (`mp_physics = 8`)
    the rain-graupel collection tables `tcg_racg, tmr_racg, tcr_gacr, tnr_racg, tnr_gacr` are
    allocated and filled with a graupel-density dimension of extent `dimNRHG = NRHG1 = 1`, but
    the eight lookups in `mp_thompson` index that dimension with `idx_bg(k)`, which the code
    sets to `idx_bg1 = 5` for this scheme. Each lookup therefore reads 4 x 37 x 37 elements
    past the intended one: a wrong table entry (the rain intercept bin shifted by 4) in most
    columns, and memory beyond the end of the table when the rain bin is the largest and the
    intercept bin is among the top four, i.e. in the heaviest rain with graupel. The crash
    instruction is the `MIN(DBLE(..*odts), table value)` that follows such a lookup. The same
    lookups are unchanged in WRF 4.5.1 to 4.7.1.
    Fix (`patches/wrf45_thompson_fix.py`, built by `scripts/setup/build_wrf_thompsonfix.sh` in a
    copy of the WRF build): read the tables at `MIN(idx_bg(k), dimNRHG)`, which is 1 here and
    unchanged (`idx_bg(k)`) for hail-aware `mp_physics = 38`; together with the two upstream
    Thompson changes of WRF 4.5.1 (commit 775826b: largest cloud-ice bin 5 -> 2 x D0s, rain
    drops made per rain-graupel collision 5 -> 1.5, the latter because too many drops gave
    evaporative cooling of about 27 K/h in NOAA tests). With the patch the WRF Thompson scheme
    is that of WRF 4.7.1 plus the bounds fix. All three WRF runs were restarted from the initial
    time with it. `tests/thompson_bounds/run.sh` runs one column (heavy rain with graupel above and
    below the melting level) through WRF 4.5's own module with Fortran bounds checking: the
    original stops with `Index '5' of dimension 3 of array 'tcg_racg' above upper bound of 1` at
    `prr_rcg(k) = tcg_racg(...)`, the lookup that the crash instruction's `MIN` follows
    (`prr_rcg(k) = MIN(DBLE(rg(k)*odts), prr_rcg(k))`); the patched module completes the step.
    All three WRF runs were then rerun from the initial time with the patched build and
    finished without a single stop (`resumes.log`: 0), well past the old crash times:
    E1 216 h (old crash 117.6 h), E2 20CRv3 144 h (74 h), E2 ERA5 144 h (8.3 and 9.05 h).

22. **WRF writes restart files every 12 simulated hours and history in 12-hour files.**
    Introduced after item 21, when all three runs had to start over: `scripts/run/run_wrf.sh`
    continues a run that stops early from the latest restart WRF wrote completely (both
    domains present and d02 stepped past it), at most 6 times, and stops instead if two attempts
    from the same restart stop at the same model time (a crash that repeats exactly is a model
    problem). Every continuation is logged in the run's `resumes.log`. The history file layout
    lets a continuation rewrite exactly the files from the restart time on
    (`write_hist_at_0h_rst = .true.`), and lets `offload.sh` move the files before the latest
    restart while WRF runs. Neither changes the simulated fields.

23. **IMD date labels are 'backward'.** `check_imd_convention.py` found the Mumbai box maximum
    (732.5 mm) on label 2005-07-27 (25: 28.9, 26: 24.8, 28: 56.9 mm), so label D holds the 24 h
    ending 03 UTC (08:30 IST) on D, as the 944 mm Santacruz report of the morning of 27 July
    requires. The config had been set to 'forward' before any data were seen. The first scoring
    run on 19 October was made with that setting although the check had failed, which compared
    every model day with the following observed day; it was discarded. `observations.imd_label`
    is now 'backward', and `score_all.py` runs the check itself and refuses to score when it
    fails.

## Measured cost

RegCM5 MOLOCH at 12 km: about 4.8 microseconds per grid-point-level step per core
(2 cores, 161 x 141 x 30, dt 90 s), inside the 4-8 us bracket used in `docs/budget.md`.
