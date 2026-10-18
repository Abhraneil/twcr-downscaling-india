#!/usr/bin/env bash
# POST-HOC, EXPLORATORY: not part of the pre-registered runs or of H1-H5 (docs/metrics.md).
#
# E2 (Mumbai 2005), ERA5-driven WRF again with the microphysics and cumulus schemes of Kumar
# et al. (2008, QJRMS), whose WRF 2.1 run from the same start time (00 UTC 24 July 2005)
# captured the Santacruz rainfall: WSM6 (mp_physics=6) on both domains and Grell-Devenyi
# (cu_physics=93) at 12 km, none at 3 km. Everything else (domains, driver, dates, radiation,
# PBL, land surface, output) is the baseline namelist; the baseline is Thompson (8) and
# Grell-Freitas (3). Both schemes change together, so a difference says the physics choice
# matters, not which of the two does.
#
#   nohup bash scripts/sensitivity/wsm6gd.sh > $TWCR_HOME/logs/sens_wsm6gd.log 2>&1 &
#
# Runs in $RUN_ROOT/wrf/E2_mumbai2005_ERA5_wsm6gd (real.exe + wrf.exe, same restart and resume
# handling as the baseline). Score it afterwards with scripts/sensitivity/score_wsm6gd.py.
set -euo pipefail
export NPROCS=${NPROCS:-12}                     # as the baseline E2 WRF runs
source "$(dirname "$0")/../run/env.sh"
EV=E2_mumbai2005; DRV=ERA5
export WRF_TAG=wsm6gd
export WRF_SED='s/^( *mp_physics *=).*/\1 6, 6,/; s/^( *cu_physics *=).*/\1 93, 0,/'

# show exactly what changes, and refuse to run if it is anything but those two lines
BASE=$REPO/namelists/wrf/namelist.input.${EV}_${DRV}
DIFF=$(diff "$BASE" <(sed -E "$WRF_SED" "$BASE") || true)
echo "$DIFF"
n=$(grep -c '^[<>]' <<< "$DIFF" || true)
grep -qE '^> +mp_physics += 6, 6,$' <<< "$DIFF" && grep -qE '^> +cu_physics += 93, 0,$' <<< "$DIFF" && [ "$n" = 4 ] \
  || { echo "namelist edit is not exactly mp_physics 6,6 and cu_physics 93,0 ($n changed lines)"; exit 1; }
echo "baseline namelist with the two lines above changed; running in $RUN_ROOT/wrf/${EV}_${DRV}_${WRF_TAG} on $NPROCS ranks"
bash "$REPO/scripts/run/run_wrf.sh" "$EV" "$DRV"
