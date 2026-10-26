#!/usr/bin/env bash
# Step 8 of the multi-event pipeline: ERA5 for the events from 1940 (Copernicus CDS; needs
# ~/.cdsapirc), into $ME_ROOT/data/drivers/.
#
#   bash multievent/08_download_era5.sh                 (events already downloaded are skipped)
#
# About 4 GB per event (0.25 deg, 37 levels, d01 plus 5 deg). CDS queues requests: expect hours
# per event; PAR events at a time (default 2). Interrupted downloads resume where they stopped.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
PAR=${PAR:-2}
[ -s "$HOME/.cdsapirc" ] || me_die "no ~/.cdsapirc (https://cds.climate.copernicus.eu/how-to-api)"
mkdir -p "$TWCR_DATA/drivers" "$ME_LOGS/download"
todo=$($ME_CASES wps-list --all --drivers ERA5 "$@" | awk '{print $1}' | while read -r e; do
  [ -s "$TWCR_DATA/drivers/${e}_ERA5.nc" ] || echo "$e"; done)
n=$(echo "$todo" | grep -c . || true)
me_log "$n events to download from CDS, $PAR at a time (logs: $ME_LOGS/download/ERA5_<event>.log)"
[ "$n" -gt 0 ] && echo "$todo" | xargs -P "$PAR" -I{} bash -c \
  "$ME_CASES download ERA5 {} > $ME_LOGS/download/ERA5_{}.log 2>&1 && echo '  done {}' || echo '  FAILED {} (see log)'"
miss=$($ME_CASES wps-list --all --drivers ERA5 "$@" | awk '{print $1}' | while read -r e; do [ -s "$TWCR_DATA/drivers/${e}_ERA5.nc" ] || echo "$e"; done | tr '\n' ' ')
[ -z "$miss" ] || me_die "missing ERA5 for: $miss (rerun to resume)"
me_log "step 8 done. Next: bash multievent/09_create_cases.sh"
