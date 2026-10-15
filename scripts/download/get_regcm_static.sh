#!/usr/bin/env bash
# Static data RegCM5 needs for this experiment, following the RegCM5 user guide
# (Doc/UserGuide/ObtainData.tex): SURFACE (terrain, land use, soil texture) and the
# CMIP6 GHG / ozone / solar forcing files. Aerosol files are not needed (iclimaaer = 0).
#   bash scripts/download/get_regcm_static.sh
set -euo pipefail
source "$(dirname "$0")/../run/env.sh"
SITE=${ICTP_DATASITE:-http://clima-dods.ictp.it/regcm4}
mkdir -p "$RCMDATA/SURFACE" "$RCMDATA/CMIP6"
cd "$RCMDATA/SURFACE"
for f in GMTED_DEM_30s.nc GLCC_BATS_30s.nc GLZB_SOIL_30s.nc; do
  [ -s "$f" ] || curl -fL -o "$f" "$SITE/SURFACE/$f"
done
cd "$RCMDATA/CMIP6"
for dir in GHG O3 SOLAR; do
  mkdir -p "$dir"
  wget -q "$SITE/CMIP6/$dir/" -O - | \
    wget -nc -A ".nc" -l1 --no-parent --base="$SITE/CMIP6/$dir/" -nd -P "$dir" -i - -F
done
du -sh "$RCMDATA"/*
