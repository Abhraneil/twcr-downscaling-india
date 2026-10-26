#!/usr/bin/env bash
# Step 13 of the multi-event pipeline: daily rain of every finished case (and of its driver) on
# the IMD grid, for scoring (multievent/lib/extract.py). Cases already extracted are skipped.
#
#   bash multievent/13_extract_rain.sh            (--force redoes all)
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
"$ME_PYTHON" "$ME_REPO/multievent/lib/extract.py" "$@" 2>&1 | grep -v -i warning | tee "$ME_LOGS/13_extract.log"
me_log "step 13 done: $TWCR_DATA/daily. Scoring (criteria M1-M6) comes after the criteria are fixed."
