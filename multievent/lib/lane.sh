#!/usr/bin/env bash
# One lane of 11_run_cases.sh with ME_SCHEDULER=local: runs its cases one after another.
#
#   bash multievent/lib/lane.sh K CASE [CASE ...]
#
# Holds the lock $ME_RUNS/lanes/lane_K while it runs, so 11_run_cases.sh never starts a second
# lane K (that would put more MPI ranks on the node than it has cores). A case that is already
# running elsewhere is skipped (run_case.sh holds a lock per case).
set -uo pipefail
source "$(dirname "$0")/../00_env.sh"
K=${1:?usage: lane.sh K CASE...}; shift
mkdir -p "$ME_RUNS/lanes"
L=$ME_RUNS/lanes/lane_$K
me_lock "$L" || { echo "lane $K is already running ($(cat "$L/info" 2>/dev/null))"; exit 0; }
me_heartbeat "$L"
trap 'kill "$ME_HEARTBEAT_PID" 2>/dev/null; me_unlock "$L"' EXIT
trap 'exit 143' TERM INT
trap '' HUP
stamp() { date '+%a %d %b %H:%M'; }
for c in "$@"; do
  echo "[$(stamp)] start $c"
  rc=0; bash "$ME_REPO/multievent/lib/run_case.sh" "$c" || rc=$?
  case $rc in
    0) echo "[$(stamp)] done  $c" ;;
    3) echo "[$(stamp)] skip  $c (running elsewhere)" ;;
    *) echo "[$(stamp)] FAILED $c (status $rc; $ME_RUNS/cases/$c/failed.txt, run.log)" ;;
  esac
done
echo "[$(stamp)] lane $K finished"
