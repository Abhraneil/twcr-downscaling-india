# Site settings. Edit once, then `source scripts/run/env.sh` before any run script.
# Defaults are for the single 64-core PBS node described in docs/runbook.md.

export REPO=${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
export RUN_ROOT=${RUN_ROOT:-$HOME/twcr_runs}            # all model run directories and output
export WPS_DIR=${WPS_DIR:-$HOME/WPS}                    # built WPS (geogrid.exe, metgrid.exe, util/rd_intermediate.exe)
export WRF_DIR=${WRF_DIR:-$HOME/WRF}                    # built WRF (main/real.exe, main/wrf.exe, run/)
export WPS_GEOG=${WPS_GEOG:-/home/abhraneil.bhattacharya/WRFCHEM/WPS_GEOG}
export REGCM_BIN=${REGCM_BIN:-$HOME/RegCM/bin}          # terrain, sst, icbc, regcm
export RCMDATA=${RCMDATA:-$HOME/RCMDATA}                # SURFACE/ and CMIP6/ from scripts/download/get_regcm_static.sh
export NPROCS=${NPROCS:-64}
export MPIRUN=${MPIRUN:-mpirun}                         # MPICH: mpirun / mpiexec
export PYTHON=${PYTHON:-python3}
