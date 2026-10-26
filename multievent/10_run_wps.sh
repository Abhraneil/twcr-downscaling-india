#!/usr/bin/env bash
# Step 10 of the multi-event pipeline: WPS for every event and driver of the created cases.
#   geogrid   once per event (both domains) in $ME_ROOT/runs/wps/<event>/
#   to_wps.py the driver's intermediate files (scripts/preprocess/to_wps.py; no ungrib), read back
#             with WPS's rd_intermediate.exe
#   metgrid   in $ME_ROOT/runs/wps/<event>/<driver>/; the intermediate files are then deleted
#
#   bash multievent/10_run_wps.sh                        every event x driver with cases
#   bash multievent/10_run_wps.sh --events A1_kerala1924
#
# PAR pairs at a time (default 4; WPS is serial). Finished work is marked with hashes of the
# namelist it was made from (cases.py wps-key): wps/<event>/.geogrid_ok (the geogrid part) and
# wps/<event>/<driver>/.wps_ok (all of it), so a pair is redone whenever 09_create_cases.sh
# --force has changed its settings, and real.exe (lib/run_case.sh) refuses met_em files without
# a matching .wps_ok. met_em files take about 5 GB per pair: 14_cleanup.sh removes them once
# every case of the pair has finished.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
PAR=${PAR:-4}

geogrid() {   # event dir, template, geogrid hash
  local G=$1 T=$2 KEY=$3 fill="s#GEO_DIR#$1#; s#WPS_GEOG_PATH#$ME_WPS_GEOG/#"
  local L=$G/.geogrid.lock k
  for k in $(seq 360); do          # the event's other driver may be running geogrid: wait for it
    [ "$(cat "$G/.geogrid_ok" 2>/dev/null)" = "$KEY" ] && return 0
    if me_lock "$L"; then
      trap "me_unlock '$L'" EXIT
      if [ "$(cat "$G/.geogrid_ok" 2>/dev/null)" != "$KEY" ]; then   # again, now that it is ours
        rm -f "$G/.geogrid_ok" "$G"/geo_em.d0* "$G"/geogrid.log*
        ( cd "$G" && sed "$fill" "$T" > namelist.wps && mkdir -p geogrid \
          && ln -sf "$ME_WPS_DIR/geogrid/GEOGRID.TBL.ARW" geogrid/GEOGRID.TBL \
          && { "$ME_WPS_DIR/geogrid.exe" > geogrid.out 2>&1 || true; } )
        if grep -q "Successful completion of geogrid" "$G"/geogrid.out "$G"/geogrid.log* 2>/dev/null \
           && [ -f "$G/geo_em.d01.nc" ] && [ -f "$G/geo_em.d02.nc" ]; then
          echo "$KEY" > "$G/.geogrid_ok"
        else
          tail -15 "$G/geogrid.out"; me_unlock "$L"; me_die "$(basename "$G"): geogrid failed ($G/geogrid.out)"
        fi
      fi
      me_unlock "$L"; trap - EXIT
      return 0
    fi
    sleep 10
  done
  me_die "$(basename "$G"): waited 1 h for geogrid ($L)"
}

one() {
  local E=$1 DRV=$2
  local G=$ME_RUNS/wps/$E W=$ME_RUNS/wps/$E/$DRV
  local T=$W/namelist.wps.template
  [ -f "$T" ] || me_die "$E $DRV: no namelist.wps.template (run 09_create_cases.sh)"
  local DF=$TWCR_DATA/drivers/${E}_${DRV}.nc
  [ -s "$DF" ] || me_die "$E $DRV: no driver file $DF (steps 7-8)"
  local FULL GEO N
  read -r FULL GEO <<< "$($ME_CASES wps-key "$T")"
  N=$("$ME_PYTHON" - "$T" <<'PY'
import re, sys
from datetime import datetime
t = open(sys.argv[1]).read()
s, e = (datetime.strptime(re.search(rf"{k}\s*=\s*'([^']+)'", t).group(1), "%Y-%m-%d_%H:%M:%S") for k in ("start_date", "end_date"))
print(int((e - s).total_seconds() // 10800) + 1)
PY
)
  if [ "$(cat "$W/.wps_ok" 2>/dev/null)" = "$FULL" ] && [ "$(ls "$W"/met_em.d01.* 2>/dev/null | wc -l)" = "$N" ] \
     && [ "$(ls "$W"/met_em.d02.* 2>/dev/null | wc -l)" = "$N" ]; then
    echo "  $E $DRV: met_em files already there"; return 0
  fi
  geogrid "$G" "$T" "$GEO"
  cd "$W"
  rm -f .wps_ok met_em.d0* metgrid.log*
  sed "s#GEO_DIR#$G#; s#WPS_GEOG_PATH#$ME_WPS_GEOG/#" namelist.wps.template > namelist.wps
  mkdir -p metgrid && ln -sf "$ME_WPS_DIR/metgrid/METGRID.TBL.ARW" metgrid/METGRID.TBL
  local PFX
  PFX=$(sed -n "s/^ *prefix *= *'\(.*\)'.*/\1/p" namelist.wps)
  rm -f "$PFX":*
  "$ME_PYTHON" "$ME_REPO/scripts/preprocess/to_wps.py" "$E" "$DRV" "$W" > to_wps.out 2>&1 || { tail -5 to_wps.out; me_die "$E $DRV: to_wps.py failed"; }
  local F1
  F1=$(ls | grep -E "^$PFX:" | sed -n 1p)
  "$ME_WPS_DIR/util/rd_intermediate.exe" "$F1" > rd_intermediate.out 2>&1 || true
  [ "$(grep -c "FIELD = " rd_intermediate.out)" -gt 100 ] || me_die "$E $DRV: rd_intermediate cannot read $F1"
  "$ME_WPS_DIR/metgrid.exe" > metgrid.out 2>&1 || true
  grep -q "Successful completion of metgrid" metgrid.out metgrid.log* 2>/dev/null || { tail -20 metgrid.out; me_die "$E $DRV: metgrid failed ($W/metgrid.out)"; }
  rm -f "$PFX":*
  [ "$(ls met_em.d01.* | wc -l)" = "$N" ] && [ "$(ls met_em.d02.* | wc -l)" = "$N" ] \
    || me_die "$E $DRV: $(ls met_em.d02.* | wc -l) met_em times, expected $N"
  echo "$FULL" > .wps_ok
  echo "  $E $DRV: $N met_em times"
}

if [ "${1:-}" = "--one" ]; then one "$2" "$3"; exit; fi
[ -x "$ME_WPS_DIR/metgrid.exe" ] || me_die "no WPS in $ME_WPS_DIR (step 2)"
pairs=$($ME_CASES wps-list "$@")
me_log "WPS for $(echo "$pairs" | grep -c .) event-driver pairs, $PAR at a time (log: $ME_LOGS/10_wps.log)"
echo "$pairs" | xargs -r -P "$PAR" -L 1 bash "$0" --one 2>&1 | tee -a "$ME_LOGS/10_wps.log"
bad=0
while read -r e d; do
  [ -n "$e" ] || continue
  [ "$(cat "$ME_RUNS/wps/$e/$d/.wps_ok" 2>/dev/null)" = "$($ME_CASES wps-key "$ME_RUNS/wps/$e/$d/namelist.wps.template" | cut -d' ' -f1)" ] \
    || { echo "  not done: $e $d"; bad=1; }
done <<< "$pairs"
[ "$bad" = 0 ] || me_die "WPS incomplete (see $ME_LOGS/10_wps.log)"
me_log "step 10 done. Next: bash multievent/11_run_cases.sh"
