# Shared RegCM5 helpers, sourced by run_regcm.sh and tests/integration/regcm_smoke.sh.

# FNEST (PreProc/ICBC/mod_nest.F90) opens the coarse ATM file named after the FIRST
# day of the month (monfirst), the convention of month-start climate runs. Our 12 km
# runs start mid-month, so link the month-start name to the real file. FNEST then
# finds each record by its time value, so the link is exact.
regcm_link_coarse() {   # coarse_output_dir
  local d=$1 f base dom stamp first
  for f in "$d"/*_ATM.??????????.nc; do
    [ -e "$f" ] || continue
    [ -L "$f" ] && continue
    base=$(basename "$f"); dom=${base%_ATM.*}; stamp=${base##*_ATM.}; stamp=${stamp%.nc}
    first=${stamp:0:6}0100
    [ "$stamp" = "$first" ] || ln -sfn "$base" "$d/${dom}_ATM.${first}.nc"
  done
}

# RegCM5 preprocessors can end with Fortran STOP (exit status 0) after an error, so
# success is judged by the files they must write, never by the exit code.
regcm_check_prep() {   # run_dir domname res
  local D=$1 dom=$2 res=$3
  ls "$D"/input/${dom}_DOMAIN000.nc > /dev/null 2>&1 || { echo "terrain wrote no DOMAIN file"; return 1; }
  ls "$D"/input/${dom}_ICBC.*.nc > /dev/null 2>&1 || { echo "icbc wrote no ICBC file"; strings "$D/icbc.log" | tail -5; return 1; }
  if [ "$res" = 12km ]; then
    ls "$D"/input/${dom}_SST.nc > /dev/null 2>&1 || { echo "sst wrote no SST file"; strings "$D/sst.log" | tail -5; return 1; }
  fi
  if grep -aqi "error\|terminated because of runtime" "$D"/terrain.log "$D"/sst.log "$D"/icbc.log; then
    echo "error message in preprocessing logs:"; grep -ai "error\|terminated" "$D"/*.log | head -5; return 1
  fi
}
