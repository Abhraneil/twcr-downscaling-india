#!/usr/bin/env bash
# Step 14 of the multi-event pipeline: free disk space that no later step needs.
#
#   bash multievent/14_cleanup.sh          (shows what it would delete)
#   bash multievent/14_cleanup.sh --yes    (deletes it)
#
# The met_em files of an event x driver, once every case of that pair in the study has finished
# (timing.txt) and none is running or queued. Only real.exe reads them, so a finished case can
# still be rerun after running 10_run_wps.sh again for its pair (FRESH=1 11_run_cases.sh).
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
YES=${1:-}
total=0
while read -r e d; do
  [ -n "$e" ] || continue
  W=$ME_RUNS/wps/$e/$d
  ls "$W"/met_em.d0* > /dev/null 2>&1 || continue
  pending=$($ME_CASES status --brief --all --events "$e" --drivers "$d" | awk '$2 != "done"' | wc -l)
  sz=$(du -sk "$W" | cut -f1)
  if [ "$pending" = 0 ]; then
    total=$((total + sz))
    if [ "$YES" = --yes ]; then rm -f "$W"/met_em.d0* "$W/.wps_ok"; echo "  deleted met_em of $e $d ($((sz / 1048576)) GB)"
    else echo "  would delete met_em of $e $d ($((sz / 1048576)) GB)"; fi
  else
    echo "  keeping $e $d: $pending cases of the pair not finished (or not created)"
  fi
done <<< "$($ME_CASES wps-list --all)"
me_log "$([ "$YES" = --yes ] && echo freed || echo would free) about $((total / 1048576)) GB"
