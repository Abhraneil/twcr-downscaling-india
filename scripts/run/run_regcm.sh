#!/usr/bin/env bash
#PBS -N regcm
#PBS -l select=1:ncpus=64
#PBS -l walltime=24:00:00
# RegCM5 12 km (driven by the reanalysis) then 3 km (FNEST from the 12 km run).
#   bash scripts/run/run_regcm.sh E1_kerala1924 20CRv3 [12km|03km|both]
set -euo pipefail
source "$(dirname "$0")/env.sh"
EV=$1; DRV=$2; WHICH=${3:-both}

# Driver input root: converted reanalysis in the RegCM ERA5 layout + CMIP6 forcing files
DIN=$RUN_ROOT/regcm_input
if [ ! -d "$DIN/$DRV/ERA5" ] || [ -z "$(find "$DIN/$DRV/ERA5" -name "tatm_*" -newer "$REPO/data/drivers/${EV}_${DRV}.nc" 2>/dev/null)" ]; then
  $PYTHON "$REPO/scripts/preprocess/to_regcm.py" "$EV" "$DRV" "$DIN"
fi
ln -sfn "$RCMDATA/CMIP6" "$DIN/$DRV/CMIP6"

run_one() {
  local RES=$1
  local D=$RUN_ROOT/regcm/${EV}_${DRV}_${RES}
  mkdir -p "$D/input" "$D/output" && cd "$D"
  ln -sfn "$RCMDATA" RCMDATA
  sed -e "s#DRIVER_DIR#${DIN}#" -e "s#RUN_ROOT#${RUN_ROOT}#" \
      "$REPO/namelists/regcm/${EV}_${DRV}_${RES}.in" > regcm.in
  "$REGCM_BIN/terrain" regcm.in > terrain.log 2>&1
  "$REGCM_BIN/sst" regcm.in > sst.log 2>&1
  "$REGCM_BIN/icbc" regcm.in > icbc.log 2>&1
  start=$(date +%s)
  $MPIRUN -np "$NPROCS" "$REGCM_BIN/regcm" regcm.in > regcm.log 2>&1
  grep -q "RegCM V5 simulation successfully reached end" regcm.log || { echo "RegCM $RES failed, see $D/regcm.log"; exit 1; }
  echo "wall_seconds=$(( $(date +%s) - start )) nprocs=$NPROCS" > timing.txt
  cat timing.txt
}

case $WHICH in
  12km) run_one 12km ;;
  03km) run_one 03km ;;
  both) run_one 12km; run_one 03km ;;
esac
