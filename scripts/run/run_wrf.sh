#!/usr/bin/env bash
# real.exe + wrf.exe for one event and driver (d01 12 km + d02 3 km, one-way nest).
#   NPROCS=20 bash scripts/run/run_wrf.sh E1_kerala1924 20CRv3
#   NPROCS=20 bash scripts/run/run_wrf.sh --post-hoc E2_mumbai2005_ERA5_start0725
#
# A post-hoc run (config `post_hoc_runs`) uses the met_em files of its event and driver
# (wps/<event>_<driver>) and runs in wrf/<post-hoc name> with its own namelist.
#
# wrf.exe writes restart files every 12 simulated hours and its history in 12-hour files
# aligned with them (scripts/generate_namelists.py). A restart time counts as usable once
# both domains' files exist and the run has stepped d02 past it (WRF writes restarts
# synchronously before stepping on), and is then recorded in restarts_ok.txt.
#
# If wrf.exe stops before the end, the run continues from the latest usable restart, up to
# WRF_MAX_RESUMES times (default 6); each stop is logged in resumes.log and that attempt's rsl
# files are kept in attempts/<n>/. It gives up at once if two attempts from the same restart
# stop at the same model time step: a crash that repeats exactly is a model problem to
# investigate, not something to retry. Restart files older than the latest two usable ones
# are deleted as the run goes on, and all of them when it succeeds.
#
# Calling the script again on a run that has usable restart files continues it; FRESH=1
# starts over from real.exe.
set -euo pipefail
source "$(dirname "$0")/env.sh"
if [ "${1:-}" = "--post-hoc" ]; then
  CASE=${2:?usage: run_wrf.sh --post-hoc NAME}
  read -r EV DRV < <($PYTHON - "$REPO" "$CASE" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import generate_namelists as g
c = g.wrf_cases(g.yaml.safe_load(open(sys.argv[1] + "/config/experiment.yaml")))
if sys.argv[2] in c and c[sys.argv[2]][3] is not None:
    print(c[sys.argv[2]][0], c[sys.argv[2]][2])
PY
) || true
  [ -n "${DRV:-}" ] || { echo "no post-hoc WRF run $CASE in config/experiment.yaml"; exit 1; }
else
  EV=$1; DRV=$2; CASE=${EV}_${DRV}
fi
[ -f "$REPO/namelists/wrf/namelist.input.$CASE" ] || { echo "no namelists/wrf/namelist.input.$CASE: run scripts/generate_namelists.py"; exit 1; }
[ -x "$WRF_DIR/main/wrf.exe" ] || { echo "WRF_DIR=$WRF_DIR has no main/wrf.exe (edit scripts/run/site.env)"; exit 1; }
MAX_RESUMES=${WRF_MAX_RESUMES:-6}
W=$RUN_ROOT/wps/${EV}_${DRV}
D=$RUN_ROOT/wrf/$CASE
ls "$W"/met_em.d02.* > /dev/null 2>&1 || { echo "no met_em files in $W: run run_wps.sh first"; exit 1; }
mkdir -p "$D" && cd "$D"
if [ "${FRESH:-0}" != 1 ] && grep -aqs "SUCCESS COMPLETE WRF" rsl.error.0000; then echo "WRF $CASE already finished (FRESH=1 reruns it)"; exit 0; fi
for f in "$WRF_DIR"/run/*; do
  case $(basename "$f") in namelist.input|*.exe) ;; *) ln -sf "$f" . ;; esac
done
ln -sf "$WRF_DIR/main/real.exe" "$WRF_DIR/main/wrf.exe" .
ln -sf "$W"/met_em.d0* .
NLEV=$($PYTHON -c "import netCDF4,glob; print(netCDF4.Dataset(sorted(glob.glob('met_em.d01.*'))[0]).dimensions['num_metgrid_levels'].size)")
log() { echo "[$(date '+%a %H:%M')] $*" | tee -a resumes.log; }

last_d02_time() {   # model time of the last d02 step in this attempt's rank-0 log
  { tail -c 20000 rsl.error.0000 2>/dev/null | grep -a "Timing for main" | grep -a "domain *2:" | tail -1 | awk '{print $5}'; } || true
}
verify_restarts() {
  local last f t
  last=$(last_d02_time)
  [ -n "$last" ] || return 0
  for f in wrfrst_d02_*; do
    [ -e "$f" ] || continue
    t=${f#wrfrst_d02_}
    if [ -e "wrfrst_d01_$t" ] && [[ "$t" < "$last" ]] && ! grep -qxs "$t" restarts_ok.txt; then
      echo "$t" >> restarts_ok.txt
    fi
  done
  return 0
}
latest_restart() {  # latest usable restart time whose files are still present
  local t r=""
  for t in $(sort -u restarts_ok.txt 2>/dev/null); do
    [ -e "wrfrst_d01_$t" ] && [ -e "wrfrst_d02_$t" ] && r=$t
  done
  echo "$r"
}
prune_restarts() {  # keep the latest two usable restart times
  local t
  for t in $(sort -u restarts_ok.txt 2>/dev/null | head -n -2); do rm -f "wrfrst_d01_$t" "wrfrst_d02_$t"; done
  return 0
}
remove_outputs() {  # (also the copies of files the mover has already moved)
  local f
  for f in wrfout_d0* wrfrst_d0*; do
    [ -L "$f" ] && rm -f "$(readlink -f "$f")"
    rm -f "$f"
  done
  rm -f restarts_ok.txt
}

if [ "${FRESH:-0}" = 1 ] || [ -z "$(latest_restart)" ]; then
  remove_outputs; rm -rf attempts resumes.log timing.txt
  sed "s#NUM_METGRID_LEVELS#${NLEV}#" "$REPO/namelists/wrf/namelist.input.$CASE" > namelist.input
  cp "$REPO/namelists/wrf/iofields.txt" .
  $MPIRUN -np "$NPROCS" ./real.exe
  grep -q "SUCCESS COMPLETE REAL_EM" rsl.error.0000 || { echo "real.exe failed, see $D/rsl.error.0000"; tail -20 rsl.error.0000; exit 1; }
  rm -rf real_logs && mkdir real_logs && mv rsl.* real_logs/
  log "start $CASE ($EV $DRV) on $NPROCS ranks"
else
  log "continuing $CASE from the restart files at $(latest_restart)"
fi

start=$(date +%s); n=0; prev=""
PRUNER=""
trap '[ -n "$PRUNER" ] && kill "$PRUNER" 2>/dev/null; true' EXIT
while :; do
  R=$(latest_restart)
  if [ -n "$R" ]; then
    $PYTHON "$REPO/scripts/generate_namelists.py" --wrf-restart "$CASE" "$R" | sed "s#NUM_METGRID_LEVELS#${NLEV}#" > namelist.input
  else
    sed "s#NUM_METGRID_LEVELS#${NLEV}#" "$REPO/namelists/wrf/namelist.input.$CASE" > namelist.input
  fi
  cp "$REPO/namelists/wrf/iofields.txt" .
  ( while sleep 600; do verify_restarts; prune_restarts; done ) & PRUNER=$!
  rc=0; $MPIRUN -np "$NPROCS" ./wrf.exe || rc=$?
  kill "$PRUNER" 2>/dev/null || true; wait "$PRUNER" 2>/dev/null || true; PRUNER=""
  if grep -aq "SUCCESS COMPLETE WRF" rsl.error.0000; then break; fi
  verify_restarts; prune_restarts
  stop=$(last_d02_time)
  n=$((n + 1))
  mkdir -p "attempts/$n" && cp namelist.input "attempts/$n/" && { mv rsl.* "attempts/$n/" 2>/dev/null || true; }
  log "wrf.exe stopped (exit $rc) at model time ${stop:-?}, attempt $n started from ${R:-the initial time}; rsl files in attempts/$n"
  if [ "${R:-start} ${stop:-none}" = "$prev" ]; then
    log "stopped at the same model time as the previous attempt from the same restart: not retrying"; exit 1
  fi
  [ "$n" -le "$MAX_RESUMES" ] || { log "giving up after $MAX_RESUMES resumes"; exit 1; }
  prev="${R:-start} ${stop:-none}"
  sleep "${WRF_RESUME_WAIT:-30}"
done
rm -f wrfrst_d0*
echo "wall_seconds=$(( $(date +%s) - start )) nprocs=$NPROCS resumes=$n" > timing.txt
log "WRF $CASE done: $(cat timing.txt)"
