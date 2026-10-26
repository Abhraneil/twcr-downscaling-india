#!/usr/bin/env bash
# Step 5 of the multi-event pipeline: IMD 0.25 deg daily rainfall, 1901-2015 (about 3 GB of raw
# files, the same again as netCDF), into $ME_ROOT/data/obs/imd_rain_<year>.nc.
#
#   bash multievent/05_download_imd.sh                 (years already present are skipped)
#   FIRST=1950 LAST=1960 bash multievent/05_download_imd.sh
#
# Source: imdpune.gov.in via imdlib (scripts/download/get_imd.py). If the server cannot be reached,
# put Rainfall_ind<YYYY>_rfp25.grd files in $ME_ROOT/data/raw/imd/ and rerun.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
FIRST=${FIRST:-1901}; LAST=${LAST:-2015}; PAR=${PAR:-4}
mkdir -p "$TWCR_DATA/obs"
todo=$(for y in $(seq "$FIRST" "$LAST"); do [ -s "$TWCR_DATA/obs/imd_rain_$y.nc" ] || echo "$y"; done)
n=$(echo "$todo" | grep -c . || true)
me_log "$n of $((LAST - FIRST + 1)) years to download, $PAR at a time (log: $ME_LOGS/05_imd.log)"
[ "$n" -gt 0 ] && echo "$todo" | xargs -P "$PAR" -I{} "$ME_PYTHON" "$ME_REPO/scripts/download/get_imd.py" {} >> "$ME_LOGS/05_imd.log" 2>&1 || true
miss=$(for y in $(seq "$FIRST" "$LAST"); do [ -s "$TWCR_DATA/obs/imd_rain_$y.nc" ] || echo "$y"; done | tr '\n' ' ')
[ -z "$miss" ] || me_die "still missing: $miss (see $ME_LOGS/05_imd.log)"
me_log "step 5 done: IMD $FIRST-$LAST in $TWCR_DATA/obs. Next: bash multievent/06_select_events.sh"
