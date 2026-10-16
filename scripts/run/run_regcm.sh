#!/usr/bin/env bash
# RegCM5 12 km (driven by the reanalysis) then 3 km (FNEST from the 12 km output).
#   NPROCS=16 bash scripts/run/run_regcm.sh E1_kerala1924 20CRv3 [12km|03km|both]
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$(dirname "$0")/regcm_common.sh"
EV=$1; DRV=$2; WHICH=${3:-both}

# reanalysis -> RegCM ERA5-reader layout (seconds; always regenerated so it matches the driver file)
DIN=$RUN_ROOT/regcm_input
$PYTHON "$REPO/scripts/preprocess/to_regcm.py" "$EV" "$DRV" "$DIN" > /dev/null
ln -sfn "$RCMDATA/CMIP6" "$DIN/$DRV/CMIP6"
for f in "$RCMDATA/SURFACE/GMTED_DEM_30s.nc" "$RCMDATA/CMIP6/SOLAR"; do
  [ -e "$f" ] || { echo "missing $f: run scripts/download/get_regcm_static.sh"; exit 1; }
done

run_one() {
  local RES=$1
  local D=$RUN_ROOT/regcm/${EV}_${DRV}_${RES}
  mkdir -p "$D/input" "$D/output" && cd "$D"
  ln -sfn "$RCMDATA" RCMDATA
  sed -e "s#DRIVER_DIR#${DIN}#" -e "s#RUN_ROOT#${RUN_ROOT}#" \
      "$REPO/namelists/regcm/${EV}_${DRV}_${RES}.in" > regcm.in
  [ "$RES" = 03km ] && regcm_link_coarse "$RUN_ROOT/regcm/${EV}_${DRV}_12km/output"
  for p in terrain sst icbc; do
    "$REGCM_BIN/$p" regcm.in > $p.log 2>&1 || { echo "RegCM $RES $p failed, see $D/$p.log"; tail -20 $p.log; exit 1; }
  done
  regcm_check_prep "$D" "${EV}_${DRV}_${RES}" "$RES" || { echo "RegCM $RES preprocessing failed in $D"; exit 1; }
  local start=$(date +%s)
  $REGCM_MPIRUN -np "$NPROCS" "$REGCM_BIN/regcmMPI" regcm.in > regcm.log 2>&1 || true
  grep -aq "RegCM V5 simulation successfully reached end" regcm.log || {
    echo "RegCM $RES failed, see $D/regcm.log"; strings regcm.log | tail -20; exit 1; }
  echo "wall_seconds=$(( $(date +%s) - start )) nprocs=$NPROCS" > timing.txt
  echo "RegCM $EV $DRV $RES done: $(cat timing.txt)"
}

case $WHICH in
  12km) run_one 12km ;;
  03km) run_one 03km ;;
  both) run_one 12km; run_one 03km ;;
esac
