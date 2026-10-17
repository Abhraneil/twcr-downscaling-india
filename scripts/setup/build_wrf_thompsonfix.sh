#!/usr/bin/env bash
# Copy the WRF 4.5 build, apply patches/wrf45_thompson_fix.py to Thompson microphysics and
# recompile the copy. The original build is not touched. On success scripts/run/site.env is
# pointed at the copy (the previous WRF_DIR line is kept as a comment).
#
#   bash scripts/setup/build_wrf_thompsonfix.sh        (copy + rebuild, 10-40 min)
#
# WRF_SRC: build to copy (default: WRF_DIR from site.env); WRF_FIX_DIR: the copy
# (default $TWCR_HOME/WRF-4.5-thompsonfix). The copy is compiled with the same WRF_CHEM
# setting as the original (read from the original wrf.exe), so only Thompson changes.
set -euo pipefail
source "$(dirname "$0")/../run/env.sh"
SRC=${WRF_SRC:-$WRF_DIR}
DST=${WRF_FIX_DIR:-$TWCR_HOME/WRF-4.5-thompsonfix}
JOBS=${JOBS:-16}
step() { echo "[$(date '+%H:%M')] $*"; }
[ -x "$SRC/main/wrf.exe" ] || { echo "no wrf.exe in WRF_SRC=$SRC"; exit 1; }
[ "$(cd "$SRC" && pwd)" != "$(mkdir -p "$DST" && cd "$DST" && pwd)" ] || { echo "WRF_SRC is already the patched copy"; exit 1; }
rmdir "$DST" 2>/dev/null || true

if [ ! -x "$DST/main/wrf.exe" ]; then
  step "copying $SRC ($(du -sh "$SRC" | cut -f1)) to $DST"
  cp -a "$SRC" "$DST"
fi
cd "$DST"
CHEM=0; nm main/wrf.exe 2>/dev/null | grep -qi "chem_driver" && CHEM=1
step "original build: WRF_CHEM=$CHEM"
# configure.wrf records the absolute source path; point it at the copy
if grep -q "^WRF_SRC_ROOT_DIR" configure.wrf; then
  sed -i "s#^WRF_SRC_ROOT_DIR *=.*#WRF_SRC_ROOT_DIR = $DST#" configure.wrf
fi
$PYTHON "$REPO/patches/wrf45_thompson_fix.py" phys/module_mp_thompson.F
cp "$REPO/patches/wrf45_thompson_fix.py" .
# Thompson's lookup-table files are written by wrf.exe into its run directory; none may be
# carried over from the unpatched code
rm -f run/qr_acr_qg*.dat run/qr_acr_qs*.dat run/freezeH2O.dat

step "compiling (log: $DST/compile_thompsonfix.log)"
( export WRF_CHEM=$CHEM WRF_KPP=0 WRF_EM_CORE=1 WRF_NMM_CORE=0 WRF_DA_CORE=0
  ./compile -j "$JOBS" em_real ) > compile_thompsonfix.log 2>&1 || true
for f in main/wrf.exe main/real.exe phys/module_mp_thompson.o; do
  [ -e "$f" ] && [ "$f" -nt phys/module_mp_thompson.F ] || {
    echo "$f was not rebuilt from the patched source; see compile_thompsonfix.log:"
    grep -n -m10 -iE "error|cannot|undefined" compile_thompsonfix.log; exit 1; }
done
if [ -f phys/module_mp_thompson.f90 ]; then
  grep -q "MIN(idx_bg(k),dimNRHG)" phys/module_mp_thompson.f90 || { echo "compiled source lacks the fix"; exit 1; }
fi
step "patched WRF built: $DST/main/wrf.exe"

SITE=$REPO/scripts/run/site.env
if [ -f "$SITE" ] && ! grep -q "^export WRF_DIR=$DST\$" "$SITE"; then
  sed -i "s#^export WRF_DIR=\(.*\)#\# unpatched Thompson: export WRF_DIR=\1\nexport WRF_DIR=$DST#" "$SITE"
  step "site.env: WRF_DIR=$DST"
fi
