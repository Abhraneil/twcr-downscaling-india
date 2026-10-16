#!/usr/bin/env bash
# real.exe + wrf.exe for one event and driver (d01 12 km + d02 3 km, one-way nest).
#   NPROCS=20 bash scripts/run/run_wrf.sh E1_kerala1924 20CRv3
set -euo pipefail
source "$(dirname "$0")/env.sh"
EV=$1; DRV=$2
[ -x "$WRF_DIR/main/wrf.exe" ] || { echo "WRF_DIR=$WRF_DIR has no main/wrf.exe (edit scripts/run/site.env)"; exit 1; }
W=$RUN_ROOT/wps/${EV}_${DRV}
D=$RUN_ROOT/wrf/${EV}_${DRV}
ls "$W"/met_em.d02.* > /dev/null 2>&1 || { echo "no met_em files in $W: run run_wps.sh first"; exit 1; }
mkdir -p "$D" && cd "$D"
for f in "$WRF_DIR"/run/*; do
  case $(basename "$f") in namelist.input|*.exe) ;; *) ln -sf "$f" . ;; esac
done
ln -sf "$WRF_DIR/main/real.exe" "$WRF_DIR/main/wrf.exe" .
ln -sf "$W"/met_em.d0* .

NLEV=$($PYTHON -c "import netCDF4,glob; print(netCDF4.Dataset(sorted(glob.glob('met_em.d01.*'))[0]).dimensions['num_metgrid_levels'].size)")
sed "s#NUM_METGRID_LEVELS#${NLEV}#" "$REPO/namelists/wrf/namelist.input.${EV}_${DRV}" > namelist.input
cp "$REPO/namelists/wrf/iofields.txt" .

$MPIRUN -np "$NPROCS" ./real.exe
grep -q "SUCCESS COMPLETE REAL_EM" rsl.error.0000 || { echo "real.exe failed, see $D/rsl.error.0000"; tail -20 rsl.error.0000; exit 1; }
mkdir -p real_logs && mv rsl.* real_logs/

start=$(date +%s)
$MPIRUN -np "$NPROCS" ./wrf.exe
grep -q "SUCCESS COMPLETE WRF" rsl.error.0000 || { echo "wrf.exe failed (CFL? see docs/runbook.md)"; tail -20 rsl.error.0000; exit 1; }
echo "wall_seconds=$(( $(date +%s) - start )) nprocs=$NPROCS" > timing.txt
echo "WRF $EV $DRV done: $(cat timing.txt)"
