#!/usr/bin/env bash
# Step 9 of the multi-event pipeline: create the cases (event x driver x physics set).
#
#   bash multievent/09_create_cases.sh                       all cases of study.yaml
#   bash multievent/09_create_cases.sh --physics P0          only the baseline set
#   bash multievent/09_create_cases.sh --events A1_kerala1924 --drivers 20CRv3
#
# Writes $ME_ROOT/runs/cases/<case>/ (case.json, namelist.input.template, iofields_d0?.txt),
# $ME_ROOT/runs/wps/<event>/<driver>/namelist.wps.template and $ME_ROOT/runs/cases.csv.
# An existing case whose settings would change is refused (it may have run): --force overwrites.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
$ME_CASES check
$ME_CASES events
$ME_CASES create "$@"
me_log "step 9 done. Next: bash multievent/10_run_wps.sh"
