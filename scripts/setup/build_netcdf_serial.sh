#!/usr/bin/env bash
# RegCM5 runs on Open MPI (scripts/setup/build_openmpi.sh), but the netCDF 4.9.0 and HDF5 in
# ~/WRFCHEM/libraries were built with MPICH (mpicc/mpifort, parallel I/O), so a RegCM5 linked
# to them loads MPICH and Open MPI into the same program. This builds a private, MPI-free
# zlib (only if the system has no zlib.h) + HDF5 + netCDF-C + netCDF-Fortran with plain
# gcc/gfortran as STATIC libraries in $TWCR_HOME/netcdf-serial, then rebuilds RegCM5 with
# them and Open MPI. Static linking means no new directory on PATH or LD_LIBRARY_PATH: WRF,
# WPS and everything in ~/WRFCHEM are untouched and keep using their own libraries.
#
#   bash scripts/setup/build_netcdf_serial.sh        (about 15 min with 32 cores)
#
# Sources: HDF5 and zlib from GitHub releases, netCDF from downloads.unidata.ucar.edu (with
# the identical upstream tarballs on the Ubuntu archive as fallback). If none can be reached,
# the script prints the URLs: download them elsewhere into $TWCR_HOME/src/ and rerun.
set -euo pipefail
source "$(dirname "$0")/../run/env.sh"
P=${NCSERIAL_PREFIX:-$TWCR_HOME/netcdf-serial}
OMPI=${OMPI_PREFIX:-$TWCR_HOME/openmpi-${OMPI_VERSION:-4.1.6}}
S=${REGCM_SRC:-$TWCR_HOME/regcm_src/RegCM}
LOG=$TWCR_HOME/logs
SRC=$TWCR_HOME/src
JOBS=${JOBS:-32}
mkdir -p "$LOG" "$SRC" "$P"
step() { echo "[$(date '+%H:%M')] $*"; }
[ -x "$OMPI/bin/mpif90" ] || { echo "no Open MPI at $OMPI: run scripts/setup/build_openmpi.sh first"; exit 1; }

fetch() {   # local-name url...
  local f=$1; shift
  [ -s "$SRC/$f" ] && return 0
  for u in "$@"; do
    step "downloading $u"
    if curl -fL --retry 2 -m 900 -o "$SRC/$f.part" "$u"; then mv "$SRC/$f.part" "$SRC/$f"; return 0; fi
  done
  rm -f "$SRC/$f.part"
  echo "could not download $f; fetch any of these on another machine as $SRC/$f and rerun:"
  printf '  %s\n' "$@"; exit 1
}
unpack() {  # tarball -> echo the top directory it creates under $SRC/build
  local t=$SRC/$1 d=$SRC/build top
  mkdir -p "$d"
  tar tf "$t" > "$d/.list"                     # (no pipe into head: pipefail + SIGPIPE)
  top=$(sed -e 's#^\./##' -e 's#/.*##' "$d/.list" | grep -v '^$' | sort -u | head -1)
  [ -n "$top" ] && [ "$(sed -e 's#^\./##' -e 's#/.*##' "$d/.list" | grep -v '^$' | sort -u | wc -l)" = 1 ] \
    || { echo "unexpected layout in $t" >&2; exit 1; }
  rm -rf "${d:?}/$top"; tar xf "$t" -C "$d"
  echo "$d/$top"
}
# Plain compilers and nothing inherited from the WRF environment.
export CC=gcc FC=gfortran F77=gfortran CXX=g++
unset CPPFLAGS LDFLAGS LIBS CFLAGS FCFLAGS FFLAGS NETCDF HDF5 2>/dev/null || true
CF="-O2 -fPIC"

# --- zlib (system headers are enough; otherwise a static copy) -------------------------
if [ -f /usr/include/zlib.h ]; then
  ZLIB=""
else
  fetch zlib-1.3.1.tar.gz https://github.com/madler/zlib/releases/download/v1.3.1/zlib-1.3.1.tar.gz
  if [ ! -f "$P/lib/libz.a" ]; then
    step "building zlib"
    d=$(unpack zlib-1.3.1.tar.gz)
    ( cd "$d" && CFLAGS="$CF" ./configure --prefix="$P" --static && make -j "$JOBS" && make install ) > "$LOG/ncs_zlib.log" 2>&1
  fi
  ZLIB="--with-zlib=$P"
fi

# --- HDF5 (serial, static, C only) -------------------------------------------------------
if [ ! -f "$P/lib/libhdf5.a" ]; then
  fetch hdf5-1.14.6.tar.gz https://github.com/HDFGroup/hdf5/releases/download/hdf5_1.14.6/hdf5-1.14.6.tar.gz
  d=$(unpack hdf5-1.14.6.tar.gz)
  step "building HDF5 1.14.6 serial (log: $LOG/ncs_hdf5.log)"
  ( cd "$d" && CFLAGS="$CF" ./configure --prefix="$P" --disable-shared --enable-static \
        --disable-parallel --disable-fortran --disable-cxx --enable-hl --disable-tests --disable-tools \
        --with-szlib=no $ZLIB \
      && make -j "$JOBS" && make install ) > "$LOG/ncs_hdf5.log" 2>&1 || { tail -25 "$LOG/ncs_hdf5.log"; exit 1; }
fi
DEP="-lhdf5_hl -lhdf5 -lz -ldl -lm"

# --- netCDF-C (serial, static, no remote access or plugins) -------------------------------
if [ ! -f "$P/lib/libnetcdf.a" ]; then
  fetch netcdf-c-4.9.2.tar.gz https://downloads.unidata.ucar.edu/netcdf-c/4.9.2/netcdf-c-4.9.2.tar.gz \
        http://archive.ubuntu.com/ubuntu/pool/universe/n/netcdf/netcdf_4.9.2.orig.tar.gz
  d=$(unpack netcdf-c-4.9.2.tar.gz)
  step "building netCDF-C 4.9.2 serial (log: $LOG/ncs_netcdf_c.log)"
  ( cd "$d" && CFLAGS="$CF" CPPFLAGS="-I$P/include" LDFLAGS="-L$P/lib" LIBS="$DEP" \
        ./configure --prefix="$P" --disable-shared --enable-static --enable-netcdf-4 \
        --disable-dap --disable-byterange --disable-nczarr --disable-plugins --disable-libxml2 \
        --disable-testsets --disable-examples \
      && make -j "$JOBS" && make install ) > "$LOG/ncs_netcdf_c.log" 2>&1 || { tail -25 "$LOG/ncs_netcdf_c.log"; exit 1; }
fi

# Everything a static libnetcdf needs, in link order, as netCDF-C itself reports it (it picks
# up optional system libraries such as libcurl or libbz2 when present).
NCLIBS=$("$P/bin/nc-config" --libs)

# --- netCDF-Fortran (static, built by the same gfortran as RegCM5) -------------------------
if [ ! -f "$P/lib/libnetcdff.a" ]; then
  fetch netcdf-fortran.tar.gz https://downloads.unidata.ucar.edu/netcdf-fortran/4.6.1/netcdf-fortran-4.6.1.tar.gz \
        "http://archive.ubuntu.com/ubuntu/pool/universe/n/netcdf-fortran/netcdf-fortran_4.6.0+really4.5.4+ds.orig.tar.xz"
  d=$(unpack netcdf-fortran.tar.gz)
  step "building netCDF-Fortran serial (log: $LOG/ncs_netcdf_f.log)"
  ( cd "$d" && CFLAGS="$CF" FCFLAGS="$CF" CPPFLAGS="-I$P/include" LDFLAGS="-L$P/lib" LIBS="$NCLIBS" \
        ./configure --prefix="$P" --disable-shared --enable-static \
      && make -j "$JOBS" && make install ) > "$LOG/ncs_netcdf_f.log" 2>&1 || { tail -25 "$LOG/ncs_netcdf_f.log"; exit 1; }
fi
for f in libhdf5.a libhdf5_hl.a libnetcdf.a libnetcdff.a; do [ -f "$P/lib/$f" ] || { echo "missing $P/lib/$f"; exit 1; }; done
ls "$P"/include/netcdf.mod > /dev/null
step "serial netCDF ready: $("$P/bin/nc-config" --version), $("$P/bin/nf-config" --version), HDF5 1.14.6, parallel: $("$P/bin/nc-config" --has-parallel4)"

# --- RegCM5 with Open MPI + this netCDF ------------------------------------------------------
step "rebuilding RegCM5 (logs: $LOG/regcm_ncs_*.log)"
cd "$S"
grep -q "dimension(\*), intent(in) :: a" Share/mod_posix.F90 || { echo "gfortran-11 patch missing in $S"; exit 1; }
[ "$(grep -c 'call top2btm(z0)' PreProc/ICBC/mod_nest.F90)" = 2 ] || { echo "FNEST patch missing in $S"; exit 1; }
make distclean > /dev/null 2>&1 || true
# nc-config/nf-config are taken from PATH by RegCM5's configure; LIBS repeats the static
# dependencies so its link tests pass (GNU ld applies every -L to every -l).
( export PATH="$P/bin:$PATH" NETCDF="$P" HDF5="$P"
  ./configure CC=gcc FC=gfortran MPIFC="$OMPI/bin/mpif90" --with-netcdf="$P" --with-hdf5="$P" \
      LIBS="$NCLIBS" > "$LOG/regcm_ncs_configure.log" 2>&1 || { tail -30 "$LOG/regcm_ncs_configure.log"; exit 1; }
  make -j "$JOBS" > "$LOG/regcm_ncs_make.log" 2>&1 || { grep -m5 -B3 -A3 "Error" "$LOG/regcm_ncs_make.log"; exit 1; }
  make install > "$LOG/regcm_ncs_install.log" 2>&1 )
for e in terrain sst icbc regcmMPI; do
  [ -x "bin/$e" ] || { echo "missing $S/bin/$e"; exit 1; }
  L=$(ldd "bin/$e")
  if echo "$L" | grep -qE "libmpi(fort)?\.so\.12|libnetcdf|libhdf5"; then
    echo "$e still links a shared MPICH/netCDF/HDF5 library:"; echo "$L" | grep -E "mpi|netcdf|hdf5"; exit 1
  fi
done
echo "  regcmMPI MPI libraries: $(ldd bin/regcmMPI | awk '/libmpi/{print $1}' | tr '\n' ' ')"
step "done: RegCM5 rebuilt with Open MPI and MPI-free static netCDF; no MPICH, netCDF or HDF5 shared library linked"
