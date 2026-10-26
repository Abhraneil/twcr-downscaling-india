#!/usr/bin/env bash
# Step 7 of the multi-event pipeline: 20CRv3 ensemble mean for every event (OPeNDAP subsets of
# the 36 km domain plus 5 deg, the simulation period), into $ME_ROOT/data/drivers/.
#
#   bash multievent/07_download_20crv3.sh               (events already downloaded are skipped)
#   bash multievent/07_download_20crv3.sh --events A1_kerala1924,A2_mumbai2005
#
# About 250 MB and 10-30 min per event from psl.noaa.gov; PAR events at a time (default 3).
# The data can be fetched on any machine that reaches PSL: copy $ME_ROOT/data/drivers across.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
PAR=${PAR:-3}
mkdir -p "$TWCR_DATA/drivers" "$ME_LOGS/download"
todo=$($ME_CASES wps-list --all --drivers 20CRv3 "$@" | awk '{print $1}' | while read -r e; do
  [ -s "$TWCR_DATA/drivers/${e}_20CRv3.nc" ] || echo "$e"; done)
n=$(echo "$todo" | grep -c . || true)
me_log "$n events to download from PSL, $PAR at a time (logs: $ME_LOGS/download/20CRv3_<event>.log)"
[ "$n" -gt 0 ] && echo "$todo" | xargs -P "$PAR" -I{} bash -c \
  "$ME_CASES download 20CRv3 {} > $ME_LOGS/download/20CRv3_{}.log 2>&1 && echo '  done {}' || echo '  FAILED {} (see log)'"
miss=$($ME_CASES wps-list --all --drivers 20CRv3 "$@" | awk '{print $1}' | while read -r e; do [ -s "$TWCR_DATA/drivers/${e}_20CRv3.nc" ] || echo "$e"; done | tr '\n' ' ')
[ -z "$miss" ] || me_die "missing 20CRv3 for: $miss (rerun; transfers are retried and checked)"
me_log "step 7 done. Next: bash multievent/08_download_era5.sh"
