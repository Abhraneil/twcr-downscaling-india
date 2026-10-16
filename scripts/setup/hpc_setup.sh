#!/usr/bin/env bash
# Overnight setup on the HPC node. Every stage is idempotent; re-run any stage by name.
#
#   tmux new -s twcr
#   cd ~/TWCR/twcr-downscaling-india
#   bash scripts/setup/hpc_setup.sh 2>&1 | tee ~/TWCR/setup.log          # all stages
#   bash scripts/setup/hpc_setup.sh download check                       # selected stages
#
# Stages: detect reach python regcm download check smoke wps
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
export REPO
REGCM_COMMIT=06a50b5524b8c3439da1d544bcba94ab08cc5193     # the commit tested in docs/validation.md
STAGES=${*:-detect reach python regcm download check smoke wps}
source "$REPO/scripts/run/env.sh"
mkdir -p "$TWCR_HOME/logs" "$RUN_ROOT"
LOG=$TWCR_HOME/logs
ok()   { echo "  [ OK ] $*"; }
bad()  { echo "  [FAIL] $*"; FAILS="${FAILS:-}\n  - $*"; }
hdr()  { echo; echo "=== $* ($(date '+%a %H:%M')) ==="; }

stage_detect() {
  hdr "detect toolchain and WRF/WPS builds"
  for t in gfortran gcc mpif90 mpirun nf-config nc-config git curl; do
    command -v $t > /dev/null && ok "$t: $(command -v $t)" || bad "$t not on PATH (is ENV_SCRIPT=$ENV_SCRIPT right?)"
  done
  echo "  netCDF-Fortran $(nf-config --version 2>/dev/null) at $(nf-config --prefix 2>/dev/null)"
  if [ -z "$WRF_DIR" ]; then
    mapfile -t cands < <(find "$HOME" -maxdepth 6 -path '*/main/wrf.exe' 2>/dev/null | grep -v -- '-ent' | sed 's#/main/wrf.exe##')
    echo "  WRF builds found (the '-ent' copy is excluded on purpose):"; printf '    %s\n' "${cands[@]:-none}"
    WRF_DIR=${cands[0]:-}
  fi
  if [ -z "$WPS_DIR" ]; then
    WPS_DIR=$(find "$HOME" -maxdepth 6 -name metgrid.exe -path '*WPS*' 2>/dev/null | head -1 | xargs -r dirname)
  fi
  [ -x "$WRF_DIR/main/wrf.exe" ] && ok "WRF_DIR=$WRF_DIR" || bad "no WRF build found; set WRF_DIR in scripts/run/site.env"
  [ -x "$WPS_DIR/metgrid.exe" ] && ok "WPS_DIR=$WPS_DIR" || bad "no WPS build found; set WPS_DIR in scripts/run/site.env"
  [ -d "$WPS_GEOG" ] && ok "WPS_GEOG=$WPS_GEOG" || bad "WPS_GEOG=$WPS_GEOG missing"
  if [ -x "$WRF_DIR/main/wrf.exe" ] && strings "$WRF_DIR/main/wrf.exe" | grep -qi "chem_opt"; then
    echo "  note: this WRF build includes WRF-Chem; it runs with chem_opt = 0 (the default) here"
  fi
  cat > "$REPO/scripts/run/site.env" <<EOF
# written by hpc_setup.sh on $(date); edit if a path is wrong
export WRF_DIR=$WRF_DIR
export WPS_DIR=$WPS_DIR
export WPS_GEOG=$WPS_GEOG
export TWCR_HOME=$TWCR_HOME
export PYTHON=${PYTHON_SITE:-$TWCR_HOME/venv/bin/python}
EOF
  ok "wrote scripts/run/site.env"
}

stage_reach() {
  hdr "which data servers this node can reach"
  for u in https://psl.noaa.gov/thredds/catalog/Datasets/20thC_ReanV3/catalog.xml \
           http://clima-dods.ictp.it/regcm4/SURFACE/ https://www.imdpune.gov.in/ \
           https://cds.climate.copernicus.eu/api https://github.com https://pypi.org/simple/xarray/; do
    c=$(curl -s -o /dev/null -m 25 -w "%{http_code}" "$u" || true)
    case $c in 2*|3*|401|403|405) ok "$c $u";; *) bad "unreachable ($c) $u";; esac
  done
  [ -s "$HOME/.cdsapirc" ] && ok "~/.cdsapirc present" || bad "~/.cdsapirc missing (needed for ERA5)"
}

stage_python() {
  hdr "python environment"
  local V=$TWCR_HOME/venv
  if [ ! -x "$V/bin/python" ]; then
    if command -v conda > /dev/null; then
      conda env create -q -p "$V" -f "$REPO/environment.yml" > "$LOG/python.log" 2>&1 || bad "conda env create failed (see $LOG/python.log)"
    else
      python3 -c 'import sys; assert sys.version_info >= (3, 10)' || { bad "python3 < 3.10 and no conda: install Miniforge from github.com/conda-forge/miniforge"; return; }
      python3 -m venv "$V" && "$V/bin/pip" install -q --upgrade pip > "$LOG/python.log" 2>&1
      "$V/bin/pip" install -q numpy scipy pandas xarray netCDF4 dask pyyaml f90nml matplotlib tabulate pytest "cdsapi>=0.7" imdlib >> "$LOG/python.log" 2>&1 || bad "pip install failed (see $LOG/python.log)"
    fi
  fi
  export PYTHON=$V/bin/python
  $PYTHON -c "import xarray, netCDF4, f90nml, cdsapi, imdlib; print('  xarray', xarray.__version__, 'netCDF4', netCDF4.__version__)" && ok "python packages" || bad "python packages incomplete"
  (cd "$REPO" && $PYTHON -m pytest -q 2>&1 | tail -1) | grep -q "passed" && ok "pytest" || bad "pytest failed: cd $REPO && $PYTHON -m pytest -q"
}

stage_regcm() {
  hdr "RegCM5 download and build (commit ${REGCM_COMMIT:0:7})"
  local S=$TWCR_HOME/regcm_src/RegCM
  if [ -x "$S/bin/regcmMPI" ] && [ -x "$S/bin/icbc" ]; then ok "already built: $S/bin"; return; fi
  mkdir -p "$TWCR_HOME/regcm_src"
  [ -d "$S/.git" ] || git clone -q https://github.com/ICTP/RegCM.git "$S" || { bad "git clone RegCM failed"; return; }
  ( cd "$S" && git fetch -q origin && git checkout -q "$REGCM_COMMIT" ) || { bad "commit $REGCM_COMMIT not found"; return; }
  command -v autoreconf > /dev/null || { bad "autoreconf missing: conda install -c conda-forge autoconf automake libtool (or module load autotools)"; return; }
  ( cd "$S" && ./bootstrap.sh > "$LOG/regcm_bootstrap.log" 2>&1 \
    && ./configure CC=gcc FC=gfortran MPIFC=mpif90 --with-netcdf="$(nf-config --prefix)" ${HDF5:+--with-hdf5=$HDF5} > "$LOG/regcm_configure.log" 2>&1 \
    && make -j 32 > "$LOG/regcm_make.log" 2>&1 && make install > "$LOG/regcm_install.log" 2>&1 ) \
    || { bad "RegCM build failed: see $LOG/regcm_configure.log and $LOG/regcm_make.log"; return; }
  for e in terrain sst icbc regcmMPI; do [ -x "$S/bin/$e" ] || bad "missing $S/bin/$e"; done
  ok "built $S/bin (terrain sst icbc regcmMPI)"
}

stage_download() {
  hdr "downloads (in parallel; logs in $LOG)"
  cd "$REPO"
  $PYTHON scripts/download/get_era5.py E2_mumbai2005   > "$LOG/dl_era5.log" 2>&1 & p1=$!
  $PYTHON scripts/download/get_20crv3.py E1_kerala1924 > "$LOG/dl_20cr_E1.log" 2>&1 & p2=$!
  $PYTHON scripts/download/get_20crv3.py E2_mumbai2005 > "$LOG/dl_20cr_E2.log" 2>&1 & p3=$!
  $PYTHON scripts/download/get_imd.py 1924 2005        > "$LOG/dl_imd.log" 2>&1 & p4=$!
  bash scripts/download/get_regcm_static.sh            > "$LOG/dl_regcm_static.log" 2>&1 & p5=$!
  for n in "1 era5" "2 20cr_E1" "3 20cr_E2" "4 imd" "5 regcm_static"; do
    set -- $n; pid=$(eval echo \$p$1)
    if wait $pid; then ok "$2"; else bad "$2 (see $LOG/dl_$2.log)"; tail -5 "$LOG/dl_$2.log" | sed 's/^/        /'; fi
  done
}

stage_check() {
  hdr "data checks"
  cd "$REPO"
  $PYTHON scripts/scoring/check_imd_convention.py && ok "IMD date convention matches config" \
    || bad "IMD date convention: see output above (tell Claude before scoring)"
  local T=$TWCR_HOME/check_tmp
  for c in E1_kerala1924:20CRv3 E2_mumbai2005:20CRv3 E2_mumbai2005:ERA5; do
    EV=${c%%:*}; DRV=${c##*:}
    f=$TWCR_DATA/drivers/${EV}_${DRV}.nc
    [ -s "$f" ] || { bad "$EV $DRV driver file missing"; continue; }
    $PYTHON -c "
import xarray as xr, sys; sys.path.insert(0,'scripts'); from common import check_standard
d=xr.open_dataset('$f'); check_standard(d)
print(f'  {d.attrs[\"source\"][:40]:40s} times={d.sizes[\"time\"]} levels={d.sizes[\"plev\"]} T850={float(d.T.sel(plev=85000).mean()):.1f}K q850={1000*float(d.Q.sel(plev=85000).mean()):.1f}g/kg PSFC={float(d.PSFC.mean())/100:.0f}hPa')
" && ok "$EV $DRV driver valid" || bad "$EV $DRV driver invalid"
    mkdir -p "$T/${EV}_${DRV}"
    $PYTHON scripts/preprocess/to_wps.py "$EV" "$DRV" "$T/${EV}_${DRV}" > /dev/null && ok "$EV $DRV -> WPS intermediate" || bad "$EV $DRV to_wps failed"
    if [ -x "$WPS_DIR/util/rd_intermediate.exe" ]; then
      f1=$(ls "$T/${EV}_${DRV}" | head -1)
      n=$(cd "$T/${EV}_${DRV}" && "$WPS_DIR/util/rd_intermediate.exe" "$f1" 2>/dev/null | grep -c "FIELD = ")
      [ "$n" -gt 100 ] && ok "rd_intermediate reads $n fields" || bad "rd_intermediate read $n fields"
    fi
    $PYTHON scripts/preprocess/to_regcm.py "$EV" "$DRV" "$T/regcm_input" > /dev/null && ok "$EV $DRV -> RegCM input" || bad "$EV $DRV to_regcm failed"
  done
}

stage_smoke() {
  hdr "RegCM5 smoke run on real E2 20CRv3 data, production grids, 24 h (about 30 min on 32 cores)"
  cd "$REPO"
  RUNNER="$MPIRUN -np 32" OMP_NUM_THREADS=1 bash tests/integration/regcm_smoke.sh E2_mumbai2005 20CRv3 \
    "$REGCM_BIN" "$RCMDATA" "$TWCR_HOME/smoke" full > "$LOG/smoke.log" 2>&1 \
    && ok "RegCM 12 km + 3 km, 24 h each" || bad "RegCM smoke (see $LOG/smoke.log)"
  tail -12 "$LOG/smoke.log" | sed 's/^/    /'
}

stage_wps() {
  hdr "WPS for all three cases (geogrid + metgrid; met_em ready for tomorrow)"
  cd "$REPO"
  for c in E2_mumbai2005:ERA5 E2_mumbai2005:20CRv3 E1_kerala1924:20CRv3; do
    EV=${c%%:*}; DRV=${c##*:}
    bash scripts/run/run_wps.sh "$EV" "$DRV" > "$LOG/wps_${EV}_${DRV}.log" 2>&1 \
      && ok "$(tail -1 "$LOG/wps_${EV}_${DRV}.log")" || { bad "WPS $EV $DRV (see $LOG/wps_${EV}_${DRV}.log)"; tail -8 "$LOG/wps_${EV}_${DRV}.log" | sed 's/^/    /'; }
  done
}

for s in $STAGES; do
  source "$REPO/scripts/run/env.sh"
  [ -x "$TWCR_HOME/venv/bin/python" ] && export PYTHON=$TWCR_HOME/venv/bin/python
  stage_$s
done
echo
if [ -n "${FAILS:-}" ]; then echo "SETUP FINISHED WITH PROBLEMS:"; echo -e "$FAILS"; exit 1
else echo "SETUP COMPLETE: all stages passed ($(date '+%a %H:%M')). Tomorrow: bash scripts/run/launch_all.sh"; fi
