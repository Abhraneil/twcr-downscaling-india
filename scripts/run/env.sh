# Site settings. `source scripts/run/env.sh` before any run script.
# scripts/setup/hpc_setup.sh writes the detected paths to scripts/run/site.env;
# edit that file (not this one) if a path is wrong.

export REPO=${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
[ -f "$REPO/scripts/run/site.env" ] && source "$REPO/scripts/run/site.env"

# compilers, MPICH, netCDF used to build WRF (also used to build RegCM5)
export ENV_SCRIPT=${ENV_SCRIPT:-$HOME/WRFCHEM/scripts/env_wrfchem.sh}
if [ -f "$ENV_SCRIPT" ] && [ -z "${TWCR_ENV_LOADED:-}" ]; then
  source "$ENV_SCRIPT"; export TWCR_ENV_LOADED=1
fi

export TWCR_HOME=${TWCR_HOME:-$HOME/TWCR}
export RUN_ROOT=${RUN_ROOT:-$TWCR_HOME/runs}               # all model run directories and output
export RCMDATA=${RCMDATA:-$TWCR_HOME/RCMDATA}              # RegCM SURFACE/ and CMIP6/
export REGCM_BIN=${REGCM_BIN:-$TWCR_HOME/regcm_src/RegCM/bin}
export WRF_DIR=${WRF_DIR:-}                                # plain WRF 4.5 build (NOT the -ent copy)
export WPS_DIR=${WPS_DIR:-}
export WPS_GEOG=${WPS_GEOG:-$HOME/WRFCHEM/WPS_GEOG}
export NPROCS=${NPROCS:-32}
export MPIRUN=${MPIRUN:-mpirun}
export PYTHON=${PYTHON:-python3}
export TWCR_DATA=${TWCR_DATA:-$REPO/data}
