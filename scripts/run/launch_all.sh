#!/usr/bin/env bash
# Launch all nine model runs on one 64-core node as four concurrent lanes.
# Small rank counts per run scale better than one 64-rank run at a time
# (measured on this node for WRF: 0.57 efficiency going from 32 to 64 ranks).
#
#   bash scripts/run/launch_all.sh            # starts the lanes in the background and returns
#   bash scripts/run/status.sh                # progress of every run
#
# Lane            ranks  runs                                                   est. wall (h)
#   wrf_E1          20   WRF E1 1924 20CRv3 (9 days, 12+3 km)                   13-25
#   wrf_E2_era5     12   WRF E2 2005 ERA5 (6 days)                              14-28
#   wrf_E2_20cr     12   WRF E2 2005 20CRv3                                     14-28
#   regcm           20   RegCM5 12+3 km: E2 ERA5, E2 20CRv3, E1 20CRv3 in turn  13-27
# Estimates from docs/budget.md (4-8 us per point-level-step; RegCM measured 4.8 us).
set -uo pipefail
source "$(dirname "$0")/env.sh"
L=$TWCR_HOME/logs
mkdir -p "$L"
cd "$REPO"

lane() {   # name ranks commands...
  local name=$1 np=$2; shift 2
  ( export NPROCS=$np
    for cmd in "$@"; do
      echo "[$(date '+%a %H:%M')] start: $cmd"
      if eval "$cmd"; then echo "[$(date '+%a %H:%M')] done:  $cmd"
      else echo "[$(date '+%a %H:%M')] FAILED: $cmd"; exit 1; fi
    done ) > "$L/lane_$name.log" 2>&1 &
  echo "lane $name ($np ranks) pid $! -> $L/lane_$name.log"
}

wps_if_needed() { echo "ls $RUN_ROOT/wps/$1_$2/met_em.d02.* > /dev/null 2>&1 || bash scripts/run/run_wps.sh $1 $2"; }

lane wrf_E1      ${NP_WRF_E1:-20}  "$(wps_if_needed E1_kerala1924 20CRv3)" "bash scripts/run/run_wrf.sh E1_kerala1924 20CRv3"
lane wrf_E2_era5 ${NP_WRF_E2:-12}  "$(wps_if_needed E2_mumbai2005 ERA5)"   "bash scripts/run/run_wrf.sh E2_mumbai2005 ERA5"
lane wrf_E2_20cr ${NP_WRF_E2:-12}  "$(wps_if_needed E2_mumbai2005 20CRv3)" "bash scripts/run/run_wrf.sh E2_mumbai2005 20CRv3"
lane regcm       ${NP_REGCM:-20}   "bash scripts/run/run_regcm.sh E2_mumbai2005 ERA5 both" \
                                   "bash scripts/run/run_regcm.sh E2_mumbai2005 20CRv3 both" \
                                   "bash scripts/run/run_regcm.sh E1_kerala1924 20CRv3 both"
echo "All lanes started. Check in 15 minutes: bash scripts/run/status.sh"
