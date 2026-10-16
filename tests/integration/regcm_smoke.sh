#!/usr/bin/env bash
# RegCM5 end-to-end smoke test: converted driver -> terrain/sst/icbc -> 12 km model (24 h)
# -> FNEST terrain/sst/icbc -> 3 km model (24 h). Uses the production namelists with
# three overrides: run length (24 h), smaller grids (fits a small machine; physics,
# projection, driver path and nesting are unchanged), and, only when CMIP6 forcing files
# are absent, constant GHG/solar/ozone.
#
#   bash tests/integration/regcm_smoke.sh EVENT DRIVER REGCM_BIN RCMDATA WORKDIR [full]
# 'full' keeps the production grid sizes (use this on the HPC with mpirun).
set -euo pipefail
EV=$1; DRV=$2; BIN=$3; RCMDATA=$4; W=$5; FULL=${6:-small}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
source "$REPO/scripts/run/regcm_common.sh"
RUNNER=${RUNNER:-}                      # e.g. "mpirun -np 32"; empty = single process (OpenMP)
mkdir -p "$W"
${PYTHON:-python3} "$REPO/scripts/preprocess/to_regcm.py" "$EV" "$DRV" "$W/regcm_input" > /dev/null
ln -sfn "$RCMDATA/CMIP6" "$W/regcm_input/$DRV/CMIP6" 2>/dev/null || true

patch_nml() {   # file res
${PYTHON:-python3} - "$1" "$2" "$FULL" "$RCMDATA" "$EV" <<'EOF'
import sys, os, f90nml, yaml
from datetime import datetime, timedelta
f, res, full, rcmdata, ev = sys.argv[1:6]
n = f90nml.read(f)
s = str(n['restartparam']['mdate1'])
e = (datetime.strptime(s, "%Y%m%d%H") + timedelta(days=1)).strftime("%Y%m%d%H")
n['restartparam']['mdate2'] = int(e)
n['globdatparam']['gdate2'] = int(e)
if full != 'full':
    if res == '12km':
        n['dimparam'].update(iy=141, jx=161)          # 1920 x 1680 km
        cfg = yaml.safe_load(open(os.path.join(os.path.dirname(f), 'experiment.yaml')))
        c = cfg['events'][ev]['inner_center']
        n['geoparam'].update(clat=c['lat'], clon=c['lon'])
    else:
        n['dimparam'].update(iy=81, jx=81)            # 240 km
need = ['GHG', 'O3', 'SOLAR']
if not all(os.path.isdir(os.path.join(rcmdata, 'CMIP6', d)) for d in need):
    n['physicsparam'].update(iclimao3=0, isolconst=1, scenario='CONST')
    print('  CMIP6 forcing files absent: smoke test uses constant GHG/solar, no ozone climatology')
n.write(f, force=True)
EOF
}

run_res() {
  local RES=$1
  local D=$W/runs/regcm/${EV}_${DRV}_${RES}
  mkdir -p "$D/input" "$D/output"
  ln -sfn "$RCMDATA" "$D/RCMDATA"
  sed -e "s#DRIVER_DIR#$W/regcm_input#" -e "s#RUN_ROOT#$W/runs#" \
      "$REPO/namelists/regcm/${EV}_${DRV}_${RES}.in" > "$D/regcm.in"
  cp "$REPO/config/experiment.yaml" "$D/experiment.yaml"
  patch_nml "$D/regcm.in" "$RES"
  cd "$D"
  [ "$RES" = 03km ] && regcm_link_coarse "$W/runs/regcm/${EV}_${DRV}_12km/output"
  for p in terrain sst icbc; do
    "$BIN/$p" regcm.in > $p.log 2>&1 || { echo "$RES $p FAILED"; tail -20 $p.log; exit 1; }
  done
  regcm_check_prep "$D" "${EV}_${DRV}_${RES}" "$RES" || { echo "$RES preprocessing FAILED"; exit 1; }
  echo "$RES preprocessing OK: $(ls input | tr '\n' ' ')"
  local t0=$(date +%s)
  OMP_NUM_THREADS=${OMP_NUM_THREADS:-2} $RUNNER "$BIN/regcmMPI" regcm.in > regcm.log 2>&1 || true
  if grep -aq "RegCM V5 simulation successfully reached end" regcm.log; then
    echo "$RES model OK: 24 h in $(( $(date +%s) - t0 )) s"
  else
    echo "$RES model FAILED"; strings regcm.log | tail -25; exit 1
  fi
}

if [ "${SMOKE_REUSE_12KM:-0}" = 1 ] && grep -aq "successfully reached end" "$W/runs/regcm/${EV}_${DRV}_12km/regcm.log" 2>/dev/null; then
  echo "12km: reusing finished run"
else
  run_res 12km
fi
run_res 03km
${PYTHON:-python3} "$REPO/tests/integration/check_regcm_output.py" "$W/runs/regcm" "$EV" "$DRV"
