# Model availability (checked 16 October 2026)

| Model | Licence | Where | In this experiment |
|---|---|---|---|
| **WRF-ARW** | public domain (NCAR/UCAR `LICENSE.txt`) | github.com/wrf-model/WRF, WPS at github.com/wrf-model/WPS | yes; v4.5 is already built on the project HPC. Namelist keys are checked against both v4.5 and the current master Registry |
| **RegCM5** | MIT (UNESCO ICTP) | github.com/ICTP/RegCM (`AC_INIT` 5.0.0) | yes; build with MPI and netCDF, default BATS land surface (no `--enable-clm45` needed). Namelist keys are checked against the Fortran namelist declarations |
| **COSMO-CLM** | restricted | CLM-Community starter package, members-only download | **no** |
| **ICON (ICON-CLM / ICON-LAM)** | BSD-3-Clause since February 2024 | DKRZ GitLab (`icon/icon-model`, public releases) | optional follow-up, not before 24 October |

## COSMO-CLM

The COSMO-CLM source comes from the CLM-Community starter package, which can only be
downloaded after logging in as a CLM-Community member, and the full sources may not be
shared with non-members. A public GitHub repository therefore cannot contain or
reproduce a COSMO-CLM run, and getting membership is an institutional process that
does not fit the 24 October deadline.

The CLM-Community and DWD decided in 2017 to develop ICON-CLM, and support for COSMO
and COSMO-CLM is being reduced (Pham et al. 2021, GMD 14:985). ICON itself became open
source under BSD-3-Clause in February 2024. If a third model is wanted later, ICON in
limited-area/climate mode is the open and current option; it needs its own remapping of
the driver (the CLM-Community tool chain), which is why it is out of scope for now.

## Checking the namelists against the sources

```bash
git clone --depth 1 --branch v4.5 https://github.com/wrf-model/WRF.git /tmp/WRF
git clone --depth 1 https://github.com/ICTP/RegCM.git /tmp/RegCM
python scripts/check_namelists.py --wrf /tmp/WRF --regcm /tmp/RegCM
```

The GitHub Actions workflow runs the same check on every push.
