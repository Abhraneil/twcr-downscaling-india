#!/usr/bin/env bash
# real.exe + wrf.exe for one case of the multi-event study (called by 11_run_cases.sh, from a
# lane or inside a PBS/SLURM job). Adapted from scripts/run/run_wrf.sh, with the same safeguards:
#
#   bash multievent/lib/run_case.sh CASE        (CASE = <event>_<driver>_<physics>)
#
# - one run per case: the case is run under the lock <case>/.run.lock (host, pid, refreshed every
#   5 min); a second start while it is held exits with status 3 and changes nothing
# - wrf.exe writes restart files every restart_h hours; a restart time counts as usable once
#   both domains' files exist and d02 has stepped past it (recorded in restarts_ok.txt)
# - if wrf.exe stops early the run continues from the latest usable restart, up to
#   ME_MAX_RESUMES times (default 4); it gives up at once if two attempts from the same restart
#   stop at the same model time (a model problem, not something to retry)
# - a wrf.exe that writes nothing to rsl.error.0000 for ME_HANG_MIN minutes (default 90) is
#   stopped and counts as a stop
# - only real.exe needs the met_em files (and checks they come from the case's current WPS
#   settings); a continuation needs only the case directory
# - the namelists come from the stored case.json, and only while the code still writes the
#   namelist the case was created with (cases.py namelist)
# - finished runs keep no restart files. A fresh start (real.exe again, earlier output deleted)
#   happens when FRESH=1 or <case>/fresh.request exists (written by 11_run_cases.sh with FRESH=1;
#   removed once real.exe has succeeded, so a requeued job continues instead of starting over)
# - Thompson lookup tables are computed once (by the first case that needs them) and then
#   shared through $ME_THOMPSON_TABLES
# States (cases.py status): running (lock), done (timing.txt), failed (failed.txt: written on
# every unsuccessful exit, with the reason), stopped (anything else that has started).
set -euo pipefail
source "$(dirname "$0")/../00_env.sh"
CASE=${1:?usage: run_case.sh CASE}
D=$ME_RUNS/cases/$CASE
[ -f "$D/case.json" ] || me_die "no case $CASE (run 09_create_cases.sh)"
[ -x "$ME_WRF_DIR/main/wrf.exe" ] && [ -x "$ME_WRF_DIR/main/real.exe" ] || me_die "no wrf.exe/real.exe in ME_WRF_DIR=$ME_WRF_DIR"
NP=${NPROCS:-$ME_NPROCS}
MAX_RESUMES=${ME_MAX_RESUMES:-4}
HANG_MIN=${ME_HANG_MIN:-90}
cd "$D"
LOCK=$D/.run.lock
if ! me_lock "$LOCK"; then
  echo "$CASE is already running ($(cat "$LOCK/info" 2>/dev/null)); not started again"; exit 3
fi
me_heartbeat "$LOCK"
MPID="" WATCH=""
log() { echo "[$(date '+%a %d %b %H:%M')] $*" | tee -a run.log; }
fail() { echo "$*" > failed.txt; log "FAILED: $*"; exit 1; }
on_exit() {
  local rc=$?
  [ -n "$WATCH" ] && kill "$WATCH" 2>/dev/null
  [ -n "$MPID" ] && kill "$MPID" 2>/dev/null
  kill "$ME_HEARTBEAT_PID" 2>/dev/null
  if [ "$rc" != 0 ] && [ ! -f failed.txt ]; then
    echo "run_case.sh stopped with status $rc$([ "$rc" -ge 128 ] && echo ' (killed: walltime, or stopped by hand)'); 11_run_cases.sh continues it" > failed.txt
    log "stopped (status $rc)"
  fi
  me_unlock "$LOCK"
}
trap on_exit EXIT
trap 'exit 143' TERM INT HUP

FRESH=${FRESH:-0}
[ -f fresh.request ] && FRESH=1
if [ "$FRESH" != 1 ] && [ -f timing.txt ]; then echo "$CASE already finished (FRESH=1 reruns it)"; exit 0; fi
rm -f failed.txt
read -r WPSREL MP <<< "$("$ME_PYTHON" -c "import json,sys; c=json.load(open(sys.argv[1])); print(c['wps_dir'], c['physics']['mp_physics'][0])" case.json)"
W=$ME_RUNS/$WPSREL

# WRF's static tables, by name (never anything a run writes, never over a file of the case)
for f in "$ME_WRF_DIR"/run/*; do
  b=$(basename "$f")
  case $b in
    *.TBL|*.TBL_*|*.tbl|*_DATA|*_DATA_DBL|*_DATA.*|*.formatted|*.asc|*.asc_*|*.bin|*.BIN|CAMtr_volume_mixing_ratio*| \
    co2_trans|tr??t??|eclipse_besselian_elements.dat|gribmap.txt|p3_lookupTable_*) ;;
    *) continue ;;
  esac
  [ -e "$b" ] && [ ! -L "$b" ] && continue
  ln -sf "$f" .
done
ln -sf "$ME_WRF_DIR/main/real.exe" "$ME_WRF_DIR/main/wrf.exe" .
if [ "$MP" = 8 ] && [ -d "$ME_THOMPSON_TABLES" ]; then
  for t in "$ME_THOMPSON_TABLES"/*.dat; do [ -e "$t" ] && ln -sf "$t" .; done
fi
namelist() {   # [restart time]
  local out
  out=$("$ME_PYTHON" "$ME_REPO/multievent/lib/cases.py" namelist "$D" ${1:-}) || fail "no namelist (cases.py namelist): see above"
  echo "$out" | sed "s#NUM_METGRID_LEVELS#$(cat nlev.txt)#" > namelist.input
}

last_d02_time() {
  { tail -c 20000 rsl.error.0000 2>/dev/null | grep -a "Timing for main" | grep -a "domain *2:" | tail -1 | awk '{print $5}'; } || true
}
verify_restarts() {
  local last f t
  last=$(last_d02_time)
  [ -n "$last" ] || return 0
  for f in wrfrst_d02_*; do
    [ -e "$f" ] || continue
    t=${f#wrfrst_d02_}
    if [ -e "wrfrst_d01_$t" ] && [[ "$t" < "$last" ]] && ! grep -qxs "$t" restarts_ok.txt; then echo "$t" >> restarts_ok.txt; fi
  done
  return 0
}
latest_restart() {
  local t r=""
  for t in $(sort -u restarts_ok.txt 2>/dev/null); do [ -e "wrfrst_d01_$t" ] && [ -e "wrfrst_d02_$t" ] && r=$t; done
  echo "$r"
}
prune_restarts() {
  local t
  for t in $(sort -u restarts_ok.txt 2>/dev/null | head -n -2); do rm -f "wrfrst_d01_$t" "wrfrst_d02_$t"; done
  return 0
}
save_tables() {   # the first case that computed the Thompson tables shares them
  local t
  [ "$MP" = 8 ] || return 0
  ls qr_acr_qg*.dat > /dev/null 2>&1 || return 0
  [ -L "$(ls qr_acr_qg*.dat | head -1)" ] && return 0
  mkdir -p "$ME_THOMPSON_TABLES"
  for t in qr_acr_qg*.dat qr_acr_qs*.dat freezeH2O.dat; do
    [ -f "$t" ] && [ ! -e "$ME_THOMPSON_TABLES/$t" ] || continue
    cp "$t" "$ME_THOMPSON_TABLES/$t.$$" && mv -f "$ME_THOMPSON_TABLES/$t.$$" "$ME_THOMPSON_TABLES/$t"
  done
  return 0
}

verify_restarts      # the log of a run that was stopped (walltime, node failure) still vouches for its restarts
if [ "$FRESH" = 1 ] || [ -z "$(latest_restart)" ]; then
  # ---- start: real.exe, which needs the met_em files of the case's current WPS settings
  ls "$W"/met_em.d02.* > /dev/null 2>&1 || fail "no met_em files in $W: run 10_run_wps.sh --events ${WPSREL#wps/}"
  [ "$(cat "$W/.wps_ok" 2>/dev/null)" = "$($ME_CASES wps-key "$W/namelist.wps.template" | cut -d' ' -f1)" ] \
    || fail "the met_em files in $W are not from its current namelist.wps.template: run 10_run_wps.sh"
  rm -f wrfout_d0* wrfdyn_d0* wrfrst_d0* wrfinput_d0* wrfbdy_d01 restarts_ok.txt timing.txt rsl.* met_em.d0*
  rm -rf attempts real_logs
  ln -sf "$W"/met_em.d0* .
  "$ME_PYTHON" -c "import netCDF4,glob; print(netCDF4.Dataset(sorted(glob.glob('met_em.d01.*'))[0]).dimensions['num_metgrid_levels'].size)" > nlev.txt
  namelist
  log "real.exe for $CASE on $NP ranks"
  $ME_MPIRUN -n "$NP" ./real.exe > real.out 2>&1 || true
  grep -q "SUCCESS COMPLETE REAL_EM" rsl.error.0000 2>/dev/null || { tail -20 rsl.error.0000 2>/dev/null; fail "real.exe failed (rsl.error.0000)"; }
  mkdir real_logs && mv rsl.* real.out real_logs/
  rm -f met_em.d0* fresh.request
  log "start $CASE on $NP ranks"
else
  [ -s nlev.txt ] && [ -f wrfinput_d01 ] && [ -f wrfbdy_d01 ] || fail "cannot continue: nlev.txt, wrfinput_d01 or wrfbdy_d01 missing (FRESH=1 starts again)"
  if [ -f rsl.error.0000 ]; then   # the stopped run's logs
    a=1; while [ -e "attempts/$a" ]; do a=$((a + 1)); done
    mkdir -p "attempts/$a" && { mv rsl.* wrf.out namelist.input "attempts/$a/" 2>/dev/null || true; }
  fi
  log "continuing $CASE from the restart files at $(latest_restart)"
fi

watchdog() {   # every 5 min: usable restarts; stop a wrf.exe that has stopped writing its log
  local k=0
  trap - EXIT
  while sleep 300; do
    k=$((k + 1))
    [ $((k % 2)) = 0 ] && { verify_restarts; prune_restarts; }
    if [ -f rsl.error.0000 ] && [ -n "$(find rsl.error.0000 -mmin +"$HANG_MIN" 2>/dev/null)" ]; then
      log "no progress for $HANG_MIN min: stopping wrf.exe"
      kill "$1" 2>/dev/null; return 0
    fi
  done
}
start=$(date +%s); n=0; prev=""
while :; do
  R=$(latest_restart)
  namelist "$R"
  rm -f rsl.*
  $ME_MPIRUN -n "$NP" ./wrf.exe > wrf.out 2>&1 &
  MPID=$!
  watchdog "$MPID" > /dev/null 2>&1 &
  WATCH=$!
  rc=0; wait "$MPID" || rc=$?
  MPID=""
  kill "$WATCH" 2>/dev/null || true; wait "$WATCH" 2>/dev/null || true; WATCH=""
  save_tables
  if grep -aq "SUCCESS COMPLETE WRF" rsl.error.0000 2>/dev/null; then break; fi
  verify_restarts; prune_restarts
  stop=$(last_d02_time)
  n=$((n + 1))
  a=1; while [ -e "attempts/$a" ]; do a=$((a + 1)); done
  mkdir -p "attempts/$a" && cp namelist.input "attempts/$a/" && { mv rsl.* wrf.out "attempts/$a/" 2>/dev/null || true; }
  log "wrf.exe stopped (exit $rc) at model time ${stop:-?}, from ${R:-the start}; rsl files in attempts/$a"
  [ "${R:-start} ${stop:-none}" != "$prev" ] || fail "stopped at the same model time twice from the same restart (attempts/$a)"
  [ "$n" -le "$MAX_RESUMES" ] || fail "gave up after $MAX_RESUMES resumes (attempts/)"
  prev="${R:-start} ${stop:-none}"
  sleep "${ME_RESUME_WAIT:-30}"
done
rm -f wrfrst_d0*
echo "wall_seconds=$(( $(date +%s) - start )) nprocs=$NP resumes=$n host=$(hostname)" > timing.txt
log "$CASE done: $(cat timing.txt)"
