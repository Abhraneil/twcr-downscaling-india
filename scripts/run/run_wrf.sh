#!/usr/bin/env bash
#PBS -N wrf
#PBS -l select=1:ncpus=64
#PBS -l walltime=24:00:00
# real.exe + wrf.exe for one event and driver (d01 12 km + d02 3 km, one-way nest).
#   bash scripts/run/run_wrf.sh E1_kerala1924 20CRv3
set -euo pipefail
source "$(dirname "$0")/env.sh"
EV=$1; DRV=$2
W=$RUN_ROOT/wps/${EV}_${DRV}
D=$RUN_ROOT/wrf/${EV}_${DRV}
mkdir -p "$D" && cd "$D"
for f in "$WRF_DIR"/run/*; do
  case $(basename "$f") in namelist.input|*.exe) ;; *) ln -sf "$f" . ;; esac
done
ln -sf "$WRF_DIR/main/real.exe" "$WRF_DIR/main/wrf.exe" .
ln -sf "$W"/met_em.d0* .

NLEV=$(ncdump -h "$(ls met_em.d01.* | head -1)" | awk '/num_metgrid_levels =/ {print $3; exit}')
[ -n "$NLEV" ] || { echo "cannot read num_metgrid_levels"; exit 1; }
sed "s#NUM_METGRID_LEVELS#${NLEV}#" "$REPO/namelists/wrf/namelist.input.${EV}_${DRV}" > namelist.input
cp "$REPO/namelists/wrf/iofields.txt" .

$MPIRUN -np "$NPROCS" ./real.exe
grep -q "SUCCESS COMPLETE REAL_EM" rsl.error.0000 || { echo "real.exe failed"; exit 1; }
mkdir -p real_logs && mv rsl.* real_logs/

start=$(date +%s)
$MPIRUN -np "$NPROCS" ./wrf.exe
grep -q "SUCCESS COMPLETE WRF" rsl.error.0000 || { echo "wrf.exe failed (CFL? see docs/runbook.md)"; exit 1; }
echo "wall_seconds=$(( $(date +%s) - start )) nprocs=$NPROCS" > timing.txt
cat timing.txt
