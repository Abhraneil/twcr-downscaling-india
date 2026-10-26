#!/usr/bin/env bash
# Step 11 of the multi-event pipeline: start the WRF runs (real.exe + wrf.exe, multievent/lib/run_case.sh).
#
#   bash multievent/11_run_cases.sh                         every created case not finished, in study order
#   bash multievent/11_run_cases.sh --physics P0            only the baseline physics
#   bash multievent/11_run_cases.sh --cases A1_kerala1924_20CRv3_P0,A2_mumbai2005_ERA5_P0
#   FRESH=1 bash multievent/11_run_cases.sh --cases ...     start those again from real.exe (also finished ones)
#
# ME_SCHEDULER (site.env):
#   local  ME_LANES lanes in the background on this node, each running its cases one after
#          another (survives logging out; logs $ME_ROOT/logs/lane_<n>.log). A lane that is still
#          running keeps its slot: running the step again only fills the free lanes.
#   pbs    one job per case: qsub, -l $ME_PBS_RESOURCES, walltime $ME_WALLTIME, $ME_SCHED_EXTRA
#   slurm  one job per case: sbatch --nodes=1 --ntasks=$ME_NPROCS --time=$ME_WALLTIME $ME_SCHED_EXTRA
# Cases that are finished, running or queued are skipped (cases.py todo; if the scheduler does
# not answer, a case with a job is taken as queued), so the step can be run again at any time to
# (re)start whatever is not done. Each case runs under its own lock (lib/run_case.sh), so it can
# never run twice at once.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
FRESH=${FRESH:-0}
list=$($ME_CASES todo "$@" $([ "$FRESH" = 1 ] && echo --fresh)) || me_die "cases.py todo failed (see above)"
todo=()
[ -z "$list" ] || mapfile -t todo <<< "$list"
me_log "${#todo[@]} cases to start ($ME_SCHEDULER$([ "$FRESH" = 1 ] && echo ', from real.exe'))"
[ "${#todo[@]}" -gt 0 ] || exit 0
if [ "$FRESH" = 1 ]; then
  for c in "${todo[@]}"; do touch "$ME_RUNS/cases/$c/fresh.request"; done
fi

case $ME_SCHEDULER in
local)
  mkdir -p "$ME_RUNS/lanes"
  free=()
  for ((k = 0; k < ME_LANES; k++)); do
    if me_lock_live "$ME_RUNS/lanes/lane_$k"; then echo "  lane $k: still running"; else free+=("$k"); fi
  done
  [ "${#free[@]}" -gt 0 ] || { me_log "all $ME_LANES lanes are busy: run this step again when one has finished"; exit 0; }
  for ((j = 0; j < ${#free[@]}; j++)); do
    k=${free[$j]}
    lane=()
    for ((i = j; i < ${#todo[@]}; i += ${#free[@]})); do lane+=("${todo[$i]}"); done
    [ "${#lane[@]}" -gt 0 ] || continue
    nohup bash "$ME_REPO/multievent/lib/lane.sh" "$k" "${lane[@]}" >> "$ME_LOGS/lane_$k.log" 2>&1 < /dev/null &
    echo "  lane $k: ${#lane[@]} cases, pid $! -> $ME_LOGS/lane_$k.log"
  done ;;
pbs|slurm)
  for c in "${todo[@]}"; do
    d=$ME_RUNS/cases/$c
    if [ "$ME_SCHEDULER" = pbs ]; then
      cat > "$d/job.sh" <<JOB
#!/bin/bash
#PBS -N ${c:0:15}
#PBS -l $ME_PBS_RESOURCES
#PBS -l walltime=$ME_WALLTIME
#PBS -j oe
#PBS -o $d/job.out
export ME_SITE=$ME_SITE
bash $ME_REPO/multievent/lib/run_case.sh $c
JOB
      id=$(qsub $ME_SCHED_EXTRA "$d/job.sh") || me_die "qsub failed for $c"
    else
      cat > "$d/job.sh" <<JOB
#!/bin/bash
#SBATCH --job-name=$c
#SBATCH --nodes=1
#SBATCH --ntasks=$ME_NPROCS
#SBATCH --time=$ME_WALLTIME
#SBATCH --output=$d/job.out
#SBATCH --open-mode=append
export ME_SITE=$ME_SITE
bash $ME_REPO/multievent/lib/run_case.sh $c
JOB
      id=$(sbatch --parsable $ME_SCHED_EXTRA "$d/job.sh") || me_die "sbatch failed for $c"
    fi
    echo "$id" > "$d/job_id"
    echo "  $c: job $id"
  done ;;
*) me_die "ME_SCHEDULER must be local, pbs or slurm" ;;
esac
me_log "started. Progress: bash multievent/12_status.sh"
