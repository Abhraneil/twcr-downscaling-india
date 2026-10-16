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
export MPIRUN=${MPIRUN:-mpirun}                            # WRF, WPS (MPICH from ENV_SCRIPT)
# RegCM5 needs a working mpi_f08, which the HPC's MPICH 4.0.3 + gfortran 11 lacks; it runs
# with the Open MPI from scripts/setup/build_openmpi.sh when that exists. No core binding, so
# the concurrent WRF lanes and the RegCM lane do not pile onto the same cores.
OMPI=$TWCR_HOME/openmpi-${OMPI_VERSION:-4.1.6}
if [ -n "${REGCM_MPIRUN_SITE:-}" ]; then                    # explicit choice in site.env
  REGCM_MPIRUN=$REGCM_MPIRUN_SITE
elif [ -x "$OMPI/bin/mpirun" ]; then
  REGCM_MPIRUN="$OMPI/bin/mpirun --bind-to none --oversubscribe --mca btl self,vader"
else
  REGCM_MPIRUN=$MPIRUN
fi
export REGCM_MPIRUN
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}                 # MPI only; no OpenMP threads per rank
export PYTHON=${PYTHON:-python3}
export TWCR_DATA=${TWCR_DATA:-$REPO/data}
