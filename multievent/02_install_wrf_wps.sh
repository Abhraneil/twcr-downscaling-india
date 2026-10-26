#!/usr/bin/env bash
# Step 2 of the multi-event pipeline: WRF 4.5 with the Thompson fix, and WPS 4.5.
#
#   bash multievent/02_install_wrf_wps.sh 2>&1 | tee $ME_ROOT/logs/02.log     (WRF: 30-90 min)
#
# If site.env names an existing build (ME_WRF_DIR, ME_WPS_DIR) it is checked and used: WRF must
# contain patches/wrf45_thompson_fix.py (on gpu-h100: ~/TWCR/WRF-4.5-thompsonfix). Otherwise:
#   WRF 4.5  github.com/wrf-model/WRF release v4.5 -> $ME_BUILD/WRF-4.5, Thompson fix applied
#            before compiling, configure "(dmpar)" for GNU (or Intel: ME_COMPILER=intel), basic
#            nesting, ./compile -j em_real
#   WPS 4.5  github.com/wrf-model/WPS tag v4.5 -> $ME_BUILD/WPS-4.5, configure "(serial_NO_GRIB2)":
#            no GRIB2 library is needed because the intermediate files are written by Python
# Needs step 1 (NETCDF=$ME_PREFIX/netcdf, MPI on PATH).
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
JOBS=${JOBS:-8}
COMPILER=${ME_COMPILER:-gnu}
mkdir -p "$ME_BUILD" "$ME_SRC"
[ -n "${NETCDF:-}" ] && [ -d "$NETCDF/lib" ] || me_die "NETCDF not set: run 01_install_libraries.sh first"
export NETCDF WRF_EM_CORE=1 WRF_NMM_CORE=0 WRF_CHEM=0 WRF_KPP=0 WRF_DA_CORE=0
unset JASPERLIB JASPERINC 2>/dev/null || true

fixed() { grep -q "MIN(idx_bg(k),dimNRHG)" "$1/phys/module_mp_thompson.F" 2>/dev/null; }

# ------------------------------------------------------------------------------- WRF ----
if [ -x "$ME_WRF_DIR/main/wrf.exe" ] && [ -x "$ME_WRF_DIR/main/real.exe" ]; then
  fixed "$ME_WRF_DIR" || me_die "$ME_WRF_DIR has no Thompson fix (patches/wrf45_thompson_fix.py); unset ME_WRF_DIR to build one"
  me_log "WRF: using $ME_WRF_DIR (Thompson fix present)"
else
  W=$ME_BUILD/WRF-4.5
  if [ ! -f "$W/configure" ]; then
    T=$ME_SRC/WRF-v4.5.tar.gz
    [ -s "$T" ] || { me_log "downloading WRF 4.5"; curl -fL --retry 2 -m 1800 -o "$T.part" \
      https://github.com/wrf-model/WRF/releases/download/v4.5/v4.5.tar.gz && mv "$T.part" "$T"; }
    rm -rf "$ME_BUILD/WRFV4.5" "$W"
    tar xzf "$T" -C "$ME_BUILD" && mv "$ME_BUILD/WRFV4.5" "$W"
  fi
  cd "$W"
  "$ME_PYTHON" "$ME_REPO/patches/wrf45_thompson_fix.py" phys/module_mp_thompson.F
  fixed "$W" || me_die "Thompson fix not applied"
  if [ ! -f configure.wrf ]; then
    case $COMPILER in
      gnu)   PAT='GNU \(gfortran/gcc\)[[:space:]]*$' ;;
      intel) PAT='INTEL \(ifort/icc\)[[:space:]]*$' ;;
      *) me_die "ME_COMPILER must be gnu or intel" ;;
    esac
    # the menu numbers differ between WRF versions: read them from the menu itself
    # (an invalid answer makes configure print the menu again and again: keep the first 200 kB)
    printf '0\n' | ./configure 2>&1 | head -c 200000 > "$ME_LOGS/02_wrf_menu.log" || true
    OPT=$(grep -E "$PAT" "$ME_LOGS/02_wrf_menu.log" | head -1 | grep -oE '[0-9]+\. \(dmpar\)' | grep -oE '^[0-9]+' || true)
    [ -n "$OPT" ] || me_die "no '(dmpar) $COMPILER' entry in the WRF configure menu ($ME_LOGS/02_wrf_menu.log)"
    me_log "WRF configure: option $OPT ($COMPILER dmpar), basic nesting"
    printf '%s\n1\n' "$OPT" | ./configure > "$ME_LOGS/02_wrf_configure.log" 2>&1 || true
    if [ ! -f configure.wrf ] && grep -q "NETCDF4 IO features are requested" "$ME_LOGS/02_wrf_configure.log"; then
      # WRF's netCDF-4 link test wants -lhdf5 -lhdf5_hl, which some installations name differently
      # (Ubuntu: libhdf5_serial). WRF then writes classic (64-bit offset) netCDF: same contents.
      me_log "netCDF-4 link test failed: configuring WRF for classic netCDF output"
      touch .netcdf_classic
      export NETCDF_classic=1
      printf '%s\n1\n' "$OPT" | ./configure > "$ME_LOGS/02_wrf_configure.log" 2>&1 || true
    fi
    [ -f configure.wrf ] || { tail -20 "$ME_LOGS/02_wrf_configure.log"; me_die "WRF configure failed"; }
  fi
  [ -f .netcdf_classic ] && export NETCDF_classic=1
  me_log "compiling WRF em_real with $JOBS jobs (log: $W/compile.log)"
  ./compile -j "$JOBS" em_real > compile.log 2>&1 || true
  [ -x main/wrf.exe ] && [ -x main/real.exe ] || { grep -n -m 20 -iE " error|Error:" compile.log; me_die "WRF compile failed: $W/compile.log"; }
  if [ -f phys/module_mp_thompson.f90 ]; then
    grep -q "MIN(idx_bg(k),dimNRHG)" phys/module_mp_thompson.f90 || me_die "compiled Thompson source lacks the fix"
  fi
  # Thompson writes its lookup tables into the run directory; none may come from unpatched code
  rm -f run/qr_acr_qg*.dat run/qr_acr_qs*.dat run/freezeH2O.dat
  me_log "WRF built: $W/main/wrf.exe"
  ME_WRF_DIR=$W
fi

# ------------------------------------------------------------------------------- WPS ----
if [ -x "$ME_WPS_DIR/geogrid.exe" ] && [ -x "$ME_WPS_DIR/metgrid.exe" ]; then
  me_log "WPS: using $ME_WPS_DIR"
else
  P=$ME_BUILD/WPS-4.5
  if [ ! -f "$P/configure" ]; then
    rm -rf "$P"
    git clone -q --depth 1 --branch v4.5 https://github.com/wrf-model/WPS.git "$P" 2>/dev/null || {
      T=$ME_SRC/WPS-v4.5.tar.gz
      curl -fL --retry 2 -m 900 -o "$T" https://github.com/wrf-model/WPS/archive/refs/tags/v4.5.tar.gz \
        || me_die "cannot download WPS 4.5: fetch github.com/wrf-model/WPS (tag v4.5) elsewhere into $P"
      tar xzf "$T" -C "$ME_BUILD" && mv "$ME_BUILD/WPS-4.5" "$P" 2>/dev/null || true; }
  fi
  cd "$P"
  export WRF_DIR=$ME_WRF_DIR
  [ -f "$ME_WRF_DIR/.netcdf_classic" ] && export NETCDF_classic=1
  if [ ! -f configure.wps ]; then
    case $COMPILER in gnu) PAT='gfortran +\(serial_NO_GRIB2\)' ;; intel) PAT='Intel compiler +\(serial_NO_GRIB2\)' ;; esac
    printf '0\n' | ./configure 2>&1 | head -c 200000 > "$ME_LOGS/02_wps_menu.log" || true
    OPT=$(grep -E "x86_64.*$PAT" "$ME_LOGS/02_wps_menu.log" | head -1 | grep -oE '^ *[0-9]+' | tr -d ' ' || true)
    [ -n "$OPT" ] || me_die "no serial_NO_GRIB2 $COMPILER entry in the WPS configure menu ($ME_LOGS/02_wps_menu.log)"
    me_log "WPS configure: option $OPT"
    printf '%s\n' "$OPT" | ./configure > "$ME_LOGS/02_wps_configure.log" 2>&1
    [ -f configure.wps ] || { tail -20 "$ME_LOGS/02_wps_configure.log"; me_die "WPS configure failed"; }
  fi
  me_log "compiling WPS (log: $P/compile.log)"
  ./compile > compile.log 2>&1 || true
  for e in geogrid.exe metgrid.exe util/rd_intermediate.exe; do
    [ -x "$e" ] || { grep -n -m 20 -iE " error|Error:" compile.log; me_die "WPS: $e not built ($P/compile.log)"; }
  done
  me_log "WPS built: $P"
fi
me_log "step 2 done: next bash multievent/03_install_python.sh"
