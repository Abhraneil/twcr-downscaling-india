#!/usr/bin/env bash
# Move finished model output from $RUN_ROOT (on /home) to a larger disk and leave a symlink in
# place of every moved file, so the analysis scripts keep reading $RUN_ROOT unchanged.
#
# Only files that no model will open again are moved:
#   RegCM5  input/ and output/ *.nc of a run whose regcm.log reached its end; a 12 km run only
#           once the 3 km run nested on it has finished too (FNEST reads the 12 km ATM files)
#   WRF     wrfout/wrfxtrm/wrfinput/wrfbdy/wrfrst of a run with SUCCESS COMPLETE WRF
#           (nothing to do when $RUN_ROOT/wrf already points to the large disk)
#   WPS     met_em files of a case whose WRF run has finished
# A file still being written is never touched: WRF and RegCM keep one output file per domain
# open for the whole run, which is why running WRF writes directly to the large disk.
#
# The destination is shared and running WRF writes there too, so the mover never takes it
# below OFFLOAD_DEST_RESERVE_GB free (default 80): a file that would is left on /home and the
# pass says so.
#
# Each file: copy to <dest>.part, compare byte for byte (cmp), rename, delete the source,
# symlink. Only coreutils/diffutils are needed. Safe to interrupt and to rerun: the next pass
# finishes any half-moved file.
#
#   bash scripts/run/offload.sh          one pass (log: $TWCR_HOME/logs/offload.log)
#   bash scripts/run/offload.sh --loop   a pass every OFFLOAD_EVERY_H hours (default 3), and at
#                                        once whenever /home free space drops below
#                                        OFFLOAD_MIN_FREE_GB (default 40); checks every 10 min
set -uo pipefail
source "$(dirname "$0")/env.sh"
DEST=${OFFLOAD_DEST:-/Datastorage/$USER/TWCR}
EVERY_H=${OFFLOAD_EVERY_H:-3}
MIN_FREE_GB=${OFFLOAD_MIN_FREE_GB:-40}
DEST_RESERVE_GB=${OFFLOAD_DEST_RESERVE_GB:-80}
LOG=$TWCR_HOME/logs/offload.log
mkdir -p "$TWCR_HOME/logs"
say() { echo "[$(date '+%a %d %H:%M')] $*" | tee -a "$LOG"; }
free_gb() { df -P -BG "$1" 2>/dev/null | awk 'NR==2 {sub("G","",$4); print $4}'; }

move_file() {   # src (regular file under RUN_ROOT)
  local s=$1 rel d
  rel=${s#"$RUN_ROOT"/}; d=$DEST/runs/$rel
  # room check: destination free space minus this file must stay above the reserve
  if [ $(( $(free_gb "$DEST") - $(stat -c %s "$s") / 1073741824 )) -lt "$DEST_RESERVE_GB" ]; then
    KEPT=$((KEPT + 1)); return 1
  fi
  mkdir -p "$(dirname "$d")" || return 1
  cp --preserve=mode,timestamps "$s" "$d.part" || { say "  copy failed, kept: $s"; rm -f "$d.part"; return 1; }
  cmp -s "$s" "$d.part" || { say "  copy differs from source, kept: $s"; rm -f "$d.part"; return 1; }
  mv -f "$d.part" "$d" && rm -f "$s" && ln -s "$d" "$s" && MOVED=$((MOVED + 1)) && BYTES=$((BYTES + $(stat -c %s "$d")))
}

move_matching() {   # dir glob...
  local dir=$1 g f; shift
  [ -d "$dir" ] || return 0
  for g in "$@"; do
    for f in "$dir"/$g; do
      [ -f "$f" ] && [ ! -L "$f" ] && move_file "$f"
    done
  done
}

wrf_done() { grep -aqs "SUCCESS COMPLETE WRF" "$RUN_ROOT/wrf/$1/rsl.error.0000"; }
regcm_done() { grep -aqs "successfully reached end" "$RUN_ROOT/regcm/$1/regcm.log"; }

one_pass() {
  MOVED=0; BYTES=0; KEPT=0
  local r name c
  say "pass: /home free $(free_gb "$RUN_ROOT") GB, $DEST free $(free_gb "$DEST") GB"
  # RegCM5
  for r in "$RUN_ROOT"/regcm/*_12km "$RUN_ROOT"/regcm/*_03km; do
    [ -d "$r" ] || continue
    name=$(basename "$r")
    regcm_done "$name" || continue
    if [ "${name%_12km}" != "$name" ] && ! regcm_done "${name%_12km}_03km"; then continue; fi
    move_matching "$r/output" "*.nc"
    move_matching "$r/input" "*.nc"
  done
  # WRF (skipped when the wrf directory itself lives on the large disk)
  if [ -d "$RUN_ROOT/wrf" ] && [ ! -L "$RUN_ROOT/wrf" ]; then
    for r in "$RUN_ROOT"/wrf/*/; do
      c=$(basename "$r"); wrf_done "$c" || continue
      move_matching "$RUN_ROOT/wrf/$c" "wrfout_*" "wrfxtrm_*" "wrfinput_*" "wrfbdy_*" "wrfrst_*"
    done
  fi
  # WPS met_em of finished WRF cases
  for r in "$RUN_ROOT"/wps/*/; do
    c=$(basename "$r"); wrf_done "$c" || continue
    move_matching "$RUN_ROOT/wps/$c" "met_em.*"
  done
  # repair: a file whose source was deleted but whose symlink was not yet made
  if [ -d "$DEST/runs" ]; then
    find "$DEST/runs" -type f ! -name "*.part" | while read -r d; do
      s=$RUN_ROOT/${d#"$DEST/runs/"}
      [ -e "$s" ] || [ -L "$s" ] || { [ -d "$(dirname "$s")" ] && ln -s "$d" "$s" && say "  relinked $s"; }
    done
  fi
  say "  moved $MOVED files, $((BYTES / 1024 / 1024 / 1024)) GB; /home free now $(free_gb "$RUN_ROOT") GB"
  [ "$KEPT" -gt 0 ] && say "  kept $KEPT finished files on /home: $DEST would drop below the $DEST_RESERVE_GB GB reserve"
  [ "$(free_gb "$RUN_ROOT")" -lt "$MIN_FREE_GB" ] && say "  WARNING: /home below $MIN_FREE_GB GB free with nothing more that can be moved safely"
  return 0
}

locked_pass() {
  mkdir -p "$DEST/runs" || { say "cannot create $DEST/runs"; return 1; }
  ( flock -n 9 || { say "another pass is running; skipped"; exit 0; }; one_pass ) 9> "$TWCR_HOME/.offload.lock"
}

if [ "${1:-}" = "--loop" ]; then
  say "loop started: every $EVERY_H h, or at once below $MIN_FREE_GB GB free on /home; destination $DEST (kept above $DEST_RESERVE_GB GB free)"
  last=0
  while true; do
    now=$(date +%s)
    if [ $((now - last)) -ge $((EVERY_H * 3600)) ] || [ "$(free_gb "$RUN_ROOT")" -lt "$MIN_FREE_GB" ]; then
      locked_pass; last=$(date +%s)
    fi
    sleep 600
  done
else
  locked_pass
fi
