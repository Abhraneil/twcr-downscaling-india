#!/usr/bin/env bash
# Build MPICH 4.x with the Fortran 2008 bindings (`mpi_f08` module) that RegCM5 needs,
# using the same gcc/gfortran as WRF and netCDF. WRF keeps its own MPICH; only RegCM5
# is built and run with this one (REGCM_MPIRUN in scripts/run/site.env).
#   bash scripts/setup/build_mpich.sh          (about 15-20 min with 32 cores)
set -euo pipefail
source "$(dirname "$0")/../run/env.sh"
V=${MPICH_VERSION:-4.2.3}
P=$TWCR_HOME/mpich-$V
if [ -x "$P/bin/mpif90" ] && ls "$P"/include/mpi_f08.mod "$P"/lib/mpi_f08.mod > /dev/null 2>&1; then
  echo "have $P"; exit 0
fi
mkdir -p "$TWCR_HOME/src" && cd "$TWCR_HOME/src"
[ -s mpich-$V.tar.gz ] || curl -fL --retry 3 -o mpich-$V.tar.gz \
  https://github.com/pmodels/mpich/releases/download/v$V/mpich-$V.tar.gz
rm -rf mpich-$V && tar xzf mpich-$V.tar.gz && cd mpich-$V
./configure --prefix="$P" CC=gcc CXX=g++ FC=gfortran F77=gfortran \
  FFLAGS=-fallow-argument-mismatch FCFLAGS=-fallow-argument-mismatch \
  --with-device=ch3:nemesis --enable-fortran=all --disable-cxx --disable-doc \
  > "$TWCR_HOME/logs/mpich_configure.log" 2>&1
make -j "${JOBS:-32}" > "$TWCR_HOME/logs/mpich_make.log" 2>&1
make install > "$TWCR_HOME/logs/mpich_install.log" 2>&1
ls "$P"/include/mpi_f08.mod "$P"/lib/mpi_f08.mod 2>/dev/null | head -1 | grep -q . \
  || { echo "MPICH built but mpi_f08.mod missing"; exit 1; }
grep -q REGCM_MPIRUN "$REPO/scripts/run/site.env" 2>/dev/null || cat >> "$REPO/scripts/run/site.env" <<EOF
export REGCM_MPI=$P
export REGCM_MPIRUN=$P/bin/mpirun
EOF
echo "MPICH $V ready at $P (REGCM_MPIRUN written to scripts/run/site.env)"
