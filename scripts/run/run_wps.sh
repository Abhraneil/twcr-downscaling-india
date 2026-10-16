#!/usr/bin/env bash
# Geogrid + intermediate files + metgrid for one event and driver.
#   bash scripts/run/run_wps.sh E1_kerala1924 20CRv3
set -euo pipefail
source "$(dirname "$0")/env.sh"
EV=$1; DRV=$2
[ -x "$WPS_DIR/metgrid.exe" ] || { echo "WPS_DIR=$WPS_DIR has no metgrid.exe (edit scripts/run/site.env)"; exit 1; }
D=$RUN_ROOT/wps/${EV}_${DRV}
mkdir -p "$D" && cd "$D"
sed "s#WPS_GEOG_PATH#${WPS_GEOG}#" "$REPO/namelists/wps/namelist.wps.${EV}_${DRV}" > namelist.wps
mkdir -p geogrid metgrid
ln -sf "$WPS_DIR/geogrid/GEOGRID.TBL.ARW" geogrid/GEOGRID.TBL
ln -sf "$WPS_DIR/metgrid/METGRID.TBL.ARW" metgrid/METGRID.TBL

# WPS built with MPI (dmpar) can use several ranks; a serial build must run as one process
if ldd "$WPS_DIR/metgrid.exe" | grep -qi libmpi; then RUNW="$MPIRUN -np 8"; else RUNW=""; fi

if [ ! -f geo_em.d02.nc ]; then
  $RUNW "$WPS_DIR/geogrid.exe" > geogrid.out 2>&1 || true
  grep -q "Successful completion of geogrid" geogrid.log* geogrid.out 2>/dev/null || { echo "geogrid failed"; tail -20 geogrid.out; exit 1; }
fi

# intermediate files written by Python (no ungrib), then read back with WPS's own reader
$PYTHON "$REPO/scripts/preprocess/to_wps.py" "$EV" "$DRV" "$D"
FIRST=$(ls -1 | grep -E '^(TWCR|ERA5):' | head -1)
if [ -x "$WPS_DIR/util/rd_intermediate.exe" ]; then
  "$WPS_DIR/util/rd_intermediate.exe" "$FIRST" > rd_intermediate.log 2>&1
  n=$(grep -c "FIELD = " rd_intermediate.log || true)
  [ "$n" -gt 100 ] || { echo "rd_intermediate read only $n fields from $FIRST"; exit 1; }
  echo "rd_intermediate: $n fields in $FIRST"
fi

$RUNW "$WPS_DIR/metgrid.exe" > metgrid.out 2>&1 || true
grep -q "Successful completion of metgrid" metgrid.log* metgrid.out 2>/dev/null || { echo "metgrid failed"; tail -30 metgrid.out; exit 1; }
echo "WPS $EV $DRV done: $(ls met_em.d01.* | wc -l) d01 + $(ls met_em.d02.* | wc -l) d02 met_em files"
