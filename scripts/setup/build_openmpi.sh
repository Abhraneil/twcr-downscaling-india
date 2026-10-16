#!/usr/bin/env bash
# RegCM5 needs the mpi_f08 Fortran interface. On our HPC, MPICH 4.0.3 with gfortran 11.4
# returns wrong data through mpi_f08 (tests/integration/mpi_f08_check.f90 fails on every
# rank, and RegCM5 aborts in MPI_Scatterv with a negative count). WRF uses the older `mpi`
# interface and is unaffected, so WRF keeps MPICH; only RegCM5 is built and run with this
# Open MPI. Open MPI 4.1's mpi_f08 passes buffers by address (no TS 29113 descriptors).
#
#   bash scripts/setup/build_openmpi.sh          (about 25-35 min with 32 cores)
#
# 1. download and build Open MPI into $TWCR_HOME/openmpi-$V   (skipped if already there)
# 2. run mpi_f08_check with it; stop unless it prints "MPI f08 OK"
# 3. rebuild RegCM5 in $TWCR_HOME/regcm_src/RegCM against it and check what it links
# scripts/run/env.sh then uses $TWCR_HOME/openmpi-$V/bin/mpirun for RegCM5 automatically.
# If this node cannot reach download.open-mpi.org, download the tarball elsewhere and put it
# in $TWCR_HOME/src/ (URL printed below).
set -euo pipefail
source "$(dirname "$0")/../run/env.sh"
V=${OMPI_VERSION:-4.1.6}
P=${OMPI_PREFIX:-$TWCR_HOME/openmpi-$V}
S=${REGCM_SRC:-$TWCR_HOME/regcm_src/RegCM}
LOG=$TWCR_HOME/logs
JOBS=${JOBS:-32}
mkdir -p "$LOG" "$TWCR_HOME/src"
step() { echo "[$(date '+%H:%M')] $*"; }

if [ ! -x "$P/bin/mpirun" ]; then
  cd "$TWCR_HOME/src"
  T=openmpi-$V.tar.bz2
  URL=https://download.open-mpi.org/release/open-mpi/v${V%.*}/$T
  if [ ! -s "$T" ]; then
    step "downloading $URL"
    curl -fL --retry 3 -m 600 -o "$T.part" "$URL" && mv "$T.part" "$T" || {
      echo "download failed: fetch $URL on another machine and copy it to $TWCR_HOME/src/$T"; exit 1; }
  fi
  rm -rf "openmpi-$V" && tar xjf "$T" && cd "openmpi-$V"
  step "configuring Open MPI $V with $(gfortran --version | head -1)  (log: $LOG/ompi_configure.log)"
  ./configure --prefix="$P" CC=gcc CXX=g++ FC=gfortran --enable-mpi-fortran=all \
      --without-ucx --without-verbs --without-ofi --without-psm2 \
      > "$LOG/ompi_configure.log" 2>&1 || { tail -30 "$LOG/ompi_configure.log"; exit 1; }
  step "building Open MPI  (log: $LOG/ompi_make.log)"
  make -j "$JOBS" > "$LOG/ompi_make.log" 2>&1 || { grep -m5 -B3 -A3 "Error" "$LOG/ompi_make.log"; exit 1; }
  make install > "$LOG/ompi_install.log" 2>&1
fi
[ -f "$P/lib/mpi_f08.mod" ] || [ -f "$P/include/mpi_f08.mod" ] || { echo "$P has no mpi_f08.mod"; exit 1; }
RUN="$P/bin/mpirun --bind-to none --oversubscribe --mca btl self,vader"

step "checking mpi_f08 with Open MPI (the check MPICH 4.0.3 failed)"
D=$(mktemp -d "$TWCR_HOME/src/f08check.XXXX")
"$P/bin/mpif90" -O2 "$REPO/tests/integration/mpi_f08_check.f90" -o "$D/f08check"
for n in 4 32; do $RUN -np $n "$D/f08check"; done 2>&1 | tee "$LOG/ompi_f08check.log"
[ "$(grep -c 'MPI f08 OK' "$LOG/ompi_f08check.log")" = 2 ] || { echo "Open MPI also fails the mpi_f08 check: stop"; exit 1; }

step "rebuilding RegCM5 with Open MPI in $S  (logs: $LOG/regcm_ompi_*.log)"
cd "$S"
grep -q "dimension(\*), intent(in) :: a" Share/mod_posix.F90 || { echo "gfortran-11 patch missing in $S"; exit 1; }
[ "$(grep -c 'call top2btm(z0)' PreProc/ICBC/mod_nest.F90)" = 2 ] || { echo "FNEST patch missing in $S"; exit 1; }
make distclean > /dev/null 2>&1 || true
./configure CC=gcc FC=gfortran MPIFC="$P/bin/mpif90" --with-netcdf="$(nf-config --prefix)" ${HDF5:+--with-hdf5=$HDF5} \
    > "$LOG/regcm_ompi_configure.log" 2>&1 || { tail -30 "$LOG/regcm_ompi_configure.log"; exit 1; }
make -j "$JOBS" > "$LOG/regcm_ompi_make.log" 2>&1 || { grep -m5 -B3 -A3 "Error" "$LOG/regcm_ompi_make.log"; exit 1; }
make install > "$LOG/regcm_ompi_install.log" 2>&1
for e in terrain sst icbc regcmMPI; do [ -x "bin/$e" ] || { echo "missing $S/bin/$e"; exit 1; }; done
L=$(ldd bin/regcmMPI)
echo "$L" | grep -E "libmpi" | sed 's/^/  /'
echo "$L" | grep -q "libmpi_usempif08.so.40" || { echo "regcmMPI is not linked to Open MPI's mpi_f08"; exit 1; }
echo "$L" | grep -qE "libmpi(fort)?\.so\.12" && { echo "regcmMPI still links MPICH libraries"; exit 1; }
step "done: RegCM5 rebuilt with Open MPI $V; RegCM runs will use: $RUN"
