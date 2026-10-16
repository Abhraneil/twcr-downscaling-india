#!/usr/bin/env bash
# Static data RegCM5 needs for this experiment, and nothing more (about 4 GB):
#   SURFACE: terrain, land use, soil texture (read by `terrain`)
#   CMIP6:   historical GHG (5 gases), ozone for 1900-1949 and 2000-2014, solar forcing
# File names are the ones hard-coded in RegCM5 (mod_ipcc_scenario, mod_rad_o3blk, mod_sun).
#   bash scripts/download/get_regcm_static.sh
set -euo pipefail
source "$(dirname "$0")/../run/env.sh"
SITE=${ICTP_DATASITE:-http://clima-dods.ictp.it/regcm4}
get() {  # url dest
  [ -s "$2" ] && { echo "have $(basename "$2")"; return; }
  echo "get  $(basename "$2")"
  if curl -fL --retry 5 --retry-delay 20 -C - -o "$2.part" "$1"; then mv "$2.part" "$2"
  else echo "FAILED $1"; MISSING="$MISSING $(basename "$2")"; fi
}
MISSING=""
mkdir -p "$RCMDATA/SURFACE" "$RCMDATA/CMIP6/GHG" "$RCMDATA/CMIP6/O3" "$RCMDATA/CMIP6/SOLAR"
for f in GMTED_DEM_30s.nc GLCC_BATS_30s.nc GLZB_SOIL_30s.nc; do
  get "$SITE/SURFACE/$f" "$RCMDATA/SURFACE/$f"
done
for g in carbon-dioxide methane nitrous-oxide cfc11 cfc12; do
  f=mole-fraction-of-${g}-in-air_input4MIPs_GHGConcentrations_CMIP_UoM-CMIP-1-2-0_gr-0p5x360deg_000001-201412.nc
  get "$SITE/CMIP6/GHG/$f" "$RCMDATA/CMIP6/GHG/$f"
done
for p in 190001-194912 200001-201412; do
  f=vmro3_input4MIPs_ozone_CMIP_UReading-CCMI-1-0_gn_${p}.nc
  get "$SITE/CMIP6/O3/$f" "$RCMDATA/CMIP6/O3/$f"
done
f=solarforcing-ref-mon_input4MIPs_solar_CMIP_SOLARIS-HEPPA-3-2_gn_185001-229912.nc
get "$SITE/CMIP6/SOLAR/$f" "$RCMDATA/CMIP6/SOLAR/$f"
du -sh "$RCMDATA"/SURFACE "$RCMDATA"/CMIP6/*
if [ -n "$MISSING" ]; then
  echo "MISSING:$MISSING"
  echo "403 Forbidden means the site refuses this machine: run scripts/download/get_regcm_static_windows.ps1 (or the same curl lines) on another machine and copy RCMDATA here."
  exit 1
fi
