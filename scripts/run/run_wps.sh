#!/usr/bin/env bash
#PBS -N wps
#PBS -l select=1:ncpus=16
#PBS -l walltime=02:00:00
# Geogrid + intermediate files + metgrid for one event and driver.
#   bash scripts/run/run_wps.sh E1_kerala1924 20CRv3
set -euo pipefail
source "$(dirname "$0")/env.sh"
EV=$1; DRV=$2
D=$RUN_ROOT/wps/${EV}_${DRV}
mkdir -p "$D" && cd "$D"
sed "s#WPS_GEOG_PATH#${WPS_GEOG}#" "$REPO/namelists/wps/namelist.wps.${EV}_${DRV}" > namelist.wps
mkdir -p geogrid metgrid
ln -sf "$WPS_DIR/geogrid/GEOGRID.TBL.ARW" geogrid/GEOGRID.TBL
ln -sf "$WPS_DIR/metgrid/METGRID.TBL.ARW" metgrid/METGRID.TBL

[ -f geo_em.d02.nc ] || $MPIRUN -np 16 "$WPS_DIR/geogrid.exe"
grep -q "Successful completion of geogrid" geogrid.log* || { echo "geogrid failed"; exit 1; }

# intermediate files written by Python (no ungrib), then validated with WPS's own reader
$PYTHON "$REPO/scripts/preprocess/to_wps.py" "$EV" "$DRV" "$D"
FIRST=$(ls -1 "$D" | grep -E '^(TWCR|ERA5):' | head -1)
"$WPS_DIR/util/rd_intermediate.exe" "$FIRST" > rd_intermediate.log
grep -q "FIELD = TT" rd_intermediate.log || { echo "rd_intermediate could not read $FIRST"; exit 1; }

$MPIRUN -np 16 "$WPS_DIR/metgrid.exe"
grep -q "Successful completion of metgrid" metgrid.log* || { echo "metgrid failed"; exit 1; }
echo "WPS done: $(ls met_em.d0* | wc -l) met_em files in $D"
