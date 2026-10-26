#!/usr/bin/env bash
# Step 1 of the multi-event pipeline: compilers, MPI and netCDF for WRF and WPS.
#
#   bash multievent/01_install_libraries.sh 2>&1 | tee $ME_ROOT/logs/01.log
#
# Uses what the machine already has (site.env: ME_MODULES, ME_ENV_SCRIPT, or PATH) and builds
# only what is missing, into $ME_PREFIX:
#   - required tools: gcc, gfortran, make, m4, perl, csh or tcsh (WRF's compile script is csh)
#   - MPI: mpicc + mpif90 from the system; otherwise MPICH 4.1.2 is built
#   - netCDF: nc-config + nf-config (netCDF-4) from the system or $NETCDF; otherwise zlib 1.3.1,
#     HDF5 1.14.6, netCDF-C 4.9.2 and netCDF-Fortran 4.6.1 are built (shared libraries)
#   - $ME_PREFIX/netcdf: one directory with bin/ include/ lib/ of netCDF-C and -Fortran, which
#     is what WRF's and WPS's configure expect in $NETCDF. Made of links to the system files when
#     the system's netCDF-C and -Fortran live in different directories (e.g. Ubuntu packages).
# Idempotent: run it again after fixing whatever it reports.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
JOBS=${JOBS:-8}
mkdir -p "$ME_PREFIX" "$ME_SRC"
ok()  { echo "  [ OK ] $*"; }
bad() { echo "  [FAIL] $*"; FAIL=1; }
FAIL=0

me_log "tools"
for t in gcc gfortran g++ make m4 perl; do
  command -v $t > /dev/null && ok "$t: $(command -v $t)" || bad "$t not found (module load gcc / install build-essential)"
done
command -v csh > /dev/null || command -v tcsh > /dev/null && ok "csh: $(command -v csh || command -v tcsh)" \
  || bad "csh/tcsh not found: WRF cannot compile without it (module load tcsh, or conda install -c conda-forge tcsh)"
[ "$FAIL" = 0 ] || me_die "missing tools above"
echo "  gfortran $(gfortran -dumpversion), gcc $(gcc -dumpversion)"

fetch() {   # local-name url... : first URL that works
  local f=$1; shift
  [ -s "$ME_SRC/$f" ] && return 0
  for u in "$@"; do
    me_log "downloading $u"
    if curl -fL --retry 2 -m 1800 -o "$ME_SRC/$f.part" "$u"; then mv "$ME_SRC/$f.part" "$ME_SRC/$f"; return 0; fi
  done
  rm -f "$ME_SRC/$f.part"
  echo "could not download $f. Fetch one of these on a machine that can, copy it to $ME_SRC/$f and rerun:"
  printf '  %s\n' "$@"; return 1
}
unpack() {  # tarball -> echo the directory it creates under $ME_SRC/build
  local t=$ME_SRC/$1 d=$ME_SRC/build top
  mkdir -p "$d"
  tar tf "$t" > "$d/.list"                     # (not piped into head: pipefail + SIGPIPE)
  top=$(sed -e 's#^\./##' -e 's#/.*##' "$d/.list" | grep -v '^$' | sort -u | sed -n 1p)
  rm -rf "${d:?}/$top"; tar xf "$t" -C "$d"
  echo "$d/$top"
}

# ------------------------------------------------------------------------------- MPI ----
me_log "MPI"
if command -v mpicc > /dev/null && command -v mpif90 > /dev/null; then
  ok "system MPI: $(command -v mpif90) ($(mpif90 --version 2>/dev/null | head -1))"
else
  fetch mpich-4.1.2.tar.gz https://github.com/pmodels/mpich/releases/download/v4.1.2/mpich-4.1.2.tar.gz \
        https://www.mpich.org/static/downloads/4.1.2/mpich-4.1.2.tar.gz
  d=$(unpack mpich-4.1.2.tar.gz)
  me_log "building MPICH 4.1.2 (log: $ME_LOGS/01_mpich.log, 20-40 min)"
  ( cd "$d" && ./configure --prefix="$ME_PREFIX" --disable-cxx --with-device=ch3 \
        FFLAGS="-fallow-argument-mismatch" FCFLAGS="-fallow-argument-mismatch" \
      && make -j "$JOBS" && make install ) > "$ME_LOGS/01_mpich.log" 2>&1 || { tail -30 "$ME_LOGS/01_mpich.log"; me_die "MPICH build failed"; }
  export PATH=$ME_PREFIX/bin:$PATH LD_LIBRARY_PATH=$ME_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
  ok "MPICH built: $(command -v mpif90)"
fi

# ---------------------------------------------------------------------------- netCDF ----
me_log "netCDF"
NC=$ME_PREFIX/netcdf
have_nc() {   # nc-config and nf-config on PATH, netCDF-4
  command -v nc-config > /dev/null && command -v nf-config > /dev/null && [ "$(nc-config --has-nc4)" = yes ]
}
# an existing $NETCDF (e.g. from ME_ENV_SCRIPT) with its own bin/ is used as it is
if [ -n "${NETCDF:-}" ] && [ "$NETCDF" != "$NC" ] && [ -x "$NETCDF/bin/nf-config" ] && [ -x "$NETCDF/bin/nc-config" ]; then
  export PATH=$NETCDF/bin:$PATH
fi
if ! have_nc; then
  me_log "no netCDF-4 with Fortran found: building zlib, HDF5, netCDF-C, netCDF-Fortran into $ME_PREFIX"
  export CC=gcc FC=gfortran F77=gfortran CXX=g++
  P=$ME_PREFIX
  if [ ! -f /usr/include/zlib.h ] && [ ! -f "$P/include/zlib.h" ]; then
    fetch zlib-1.3.1.tar.gz https://github.com/madler/zlib/releases/download/v1.3.1/zlib-1.3.1.tar.gz
    d=$(unpack zlib-1.3.1.tar.gz)
    ( cd "$d" && ./configure --prefix="$P" && make -j "$JOBS" && make install ) > "$ME_LOGS/01_zlib.log" 2>&1 || me_die "zlib build failed"
  fi
  ZL=""; [ -f "$P/include/zlib.h" ] && ZL="--with-zlib=$P"
  if [ ! -f "$P/lib/libhdf5.so" ] && [ ! -f "$P/lib/libhdf5.a" ]; then
    fetch hdf5-1.14.6.tar.gz https://github.com/HDFGroup/hdf5/releases/download/hdf5_1.14.6/hdf5-1.14.6.tar.gz
    d=$(unpack hdf5-1.14.6.tar.gz)
    me_log "building HDF5 1.14.6 (log: $ME_LOGS/01_hdf5.log)"
    ( cd "$d" && ./configure --prefix="$P" --enable-hl --disable-fortran --disable-cxx --disable-tests \
          --disable-tools --with-szlib=no $ZL && make -j "$JOBS" && make install ) > "$ME_LOGS/01_hdf5.log" 2>&1 \
      || { tail -25 "$ME_LOGS/01_hdf5.log"; me_die "HDF5 build failed"; }
  fi
  if [ ! -x "$P/bin/nc-config" ]; then
    if fetch netcdf-c-4.9.2.tar.gz https://downloads.unidata.ucar.edu/netcdf-c/4.9.2/netcdf-c-4.9.2.tar.gz \
             http://archive.ubuntu.com/ubuntu/pool/universe/n/netcdf/netcdf_4.9.2.orig.tar.gz; then
      d=$(unpack netcdf-c-4.9.2.tar.gz)
      me_log "building netCDF-C 4.9.2 (log: $ME_LOGS/01_netcdf_c.log)"
      ( cd "$d" && CPPFLAGS="-I$P/include" LDFLAGS="-L$P/lib -Wl,-rpath,$P/lib" ./configure --prefix="$P" \
            --enable-netcdf-4 --disable-dap --disable-byterange --disable-nczarr --disable-libxml2 \
            --disable-testsets --disable-examples && make -j "$JOBS" && make install ) > "$ME_LOGS/01_netcdf_c.log" 2>&1 \
        || { tail -25 "$ME_LOGS/01_netcdf_c.log"; me_die "netCDF-C build failed"; }
    else
      me_die "no netCDF-C source"
    fi
  fi
  if [ ! -x "$P/bin/nf-config" ]; then
    if fetch netcdf-fortran-4.6.1.tar.gz https://downloads.unidata.ucar.edu/netcdf-fortran/4.6.1/netcdf-fortran-4.6.1.tar.gz \
             https://github.com/Unidata/netcdf-fortran/archive/refs/tags/v4.6.1.tar.gz; then
      d=$(unpack netcdf-fortran-4.6.1.tar.gz)
      me_log "building netCDF-Fortran 4.6.1 (log: $ME_LOGS/01_netcdf_f.log)"
      ( cd "$d" && { [ -x configure ] || autoreconf -i; } && CPPFLAGS="-I$P/include" LDFLAGS="-L$P/lib -Wl,-rpath,$P/lib" \
            ./configure --prefix="$P" && make -j "$JOBS" && make install ) > "$ME_LOGS/01_netcdf_f.log" 2>&1 \
        || { tail -25 "$ME_LOGS/01_netcdf_f.log"; me_die "netCDF-Fortran build failed"; }
    else
      me_die "no netCDF-Fortran source"
    fi
  fi
  export PATH=$P/bin:$PATH LD_LIBRARY_PATH=$P/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
fi
have_nc || me_die "netCDF still not usable (nc-config --has-nc4 = $(nc-config --has-nc4 2>/dev/null))"
ok "netCDF-C $(nc-config --version | awk '{print $2}') at $(nc-config --prefix); netCDF-Fortran $(nf-config --version | awk '{print $2}') at $(nf-config --prefix)"

# one prefix for WRF/WPS: links to wherever the files are
rm -rf "${NC:?}"; mkdir -p "$NC/bin" "$NC/include" "$NC/lib"
ln -s "$(command -v nc-config)" "$NC/bin/nc-config"
ln -s "$(command -v nf-config)" "$NC/bin/nf-config"
libdirs="$(nc-config --libdir 2>/dev/null || echo "$(nc-config --prefix)/lib") $(nf-config --flibs | tr ' ' '\n' | sed -n 's/^-L//p') $(nf-config --prefix)/lib"
incdirs="$(nc-config --includedir) $(nf-config --includedir 2>/dev/null || echo "$(nf-config --prefix)/include")"
for d in $libdirs; do
  for f in "$d"/libnetcdf*; do [ -e "$f" ] && [ ! -e "$NC/lib/$(basename "$f")" ] && ln -s "$f" "$NC/lib/"; done
done
for d in $incdirs; do
  for f in "$d"/netcdf*.h "$d"/netcdf.inc "$d"/*.mod; do [ -e "$f" ] && [ ! -e "$NC/include/$(basename "$f")" ] && ln -s "$f" "$NC/include/"; done
done
ls "$NC"/lib/libnetcdff.* > /dev/null 2>&1 || me_die "libnetcdff not found in: $libdirs"
ls "$NC"/include/netcdf.mod > /dev/null 2>&1 || me_die "netcdf.mod not found in: $incdirs"
ok "NETCDF=$NC ($(ls "$NC"/lib | wc -l) libraries, $(ls "$NC"/include | wc -l) headers/modules)"

# a two-rank MPI hello in Fortran: the compiler, MPI and launcher work together
T=$(mktemp -d)
cat > "$T/h.f90" <<'EOF'
program h
  use mpi
  integer :: r, n, e
  call mpi_init(e); call mpi_comm_rank(mpi_comm_world, r, e); call mpi_comm_size(mpi_comm_world, n, e)
  if (r == 0) print '(a,i0,a)', 'MPI hello from ', n, ' ranks'
  call mpi_finalize(e)
end program h
EOF
if (cd "$T" && mpif90 h.f90 -o h > build.log 2>&1 && $ME_MPIRUN -n 2 ./h | grep -q "from 2 ranks"); then ok "MPI Fortran hello on 2 ranks"
else bad "MPI Fortran hello failed (see $T)"; fi
[ "$FAIL" = 0 ] && { rm -rf "$T"; me_log "step 1 done: next bash multievent/02_install_wrf_wps.sh"; } || me_die "see above"
