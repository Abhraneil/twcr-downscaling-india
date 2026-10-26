#!/usr/bin/env bash
# Step 4 of the multi-event pipeline: check everything the later steps need, before any download.
#
#   bash multievent/04_check_installation.sh
#
# Checks: WRF/WPS executables and the Thompson fix, the WPS geography, MPI, Python packages,
# the scheduler, free disk space, ~/.cdsapirc, which data servers this machine can reach.
# Nothing is changed. Exit status 1 if anything a later step needs is missing.
set -uo pipefail
source "$(dirname "$0")/00_env.sh"
FAIL=0
ok()   { echo "  [ OK ] $*"; }
warn() { echo "  [WARN] $*"; }
bad()  { echo "  [FAIL] $*"; FAIL=1; }
me_log "builds"
for e in main/wrf.exe main/real.exe; do [ -x "$ME_WRF_DIR/$e" ] && ok "$ME_WRF_DIR/$e" || bad "no $ME_WRF_DIR/$e (step 2)"; done
grep -q "MIN(idx_bg(k),dimNRHG)" "$ME_WRF_DIR/phys/module_mp_thompson.F" 2>/dev/null && ok "Thompson fix in the WRF source" || bad "WRF without the Thompson fix"
for e in geogrid.exe metgrid.exe util/rd_intermediate.exe; do [ -x "$ME_WPS_DIR/$e" ] && ok "$ME_WPS_DIR/$e" || bad "no $ME_WPS_DIR/$e (step 2)"; done
for t in geogrid/GEOGRID.TBL.ARW metgrid/METGRID.TBL.ARW; do [ -f "$ME_WPS_DIR/$t" ] && ok "$t" || bad "no $ME_WPS_DIR/$t"; done
me_log "WPS geography ($ME_WPS_GEOG)"
# the data sets geogrid reads with geog_data_res = 'default', from GEOGRID.TBL.ARW itself
"$ME_PYTHON" - "$ME_WPS_DIR/geogrid/GEOGRID.TBL.ARW" "$ME_WPS_GEOG" <<'PY' || FAIL=1
import re, sys
from pathlib import Path
tbl, geog = Path(sys.argv[1]), Path(sys.argv[2])
if not tbl.exists():
    print(f"  [FAIL] no {tbl}"); sys.exit(1)
bad = 0
for sec in tbl.read_text().split("==="):
    name = re.search(r"name\s*=\s*(\S+)", sec)
    opt = re.search(r"optional\s*=\s*yes", sec)
    for rel in re.findall(r"rel_path\s*=\s*default:(\S+?)/?\s*$", sec, re.M):
        if (geog / rel).is_dir():
            continue
        tag = "WARN" if opt else "FAIL"
        bad += tag == "FAIL"
        print(f"  [{tag}] {geog / rel} missing ({name.group(1) if name else '?'}{', optional' if opt else ''})")
print(f"  [{'OK' if not bad else 'FAIL'}] WPS geography: {'all default data sets present' if not bad else f'{bad} missing'}")
if bad:
    print("         UCAR downloads are blocked here: rsync -a gpu-h100:~/WRFCHEM/WPS_GEOG/ to this machine")
sys.exit(1 if bad else 0)
PY
me_log "MPI and Python"
command -v "${ME_MPIRUN%% *}" > /dev/null && ok "MPI launcher: $ME_MPIRUN" || bad "no $ME_MPIRUN"
"$ME_PYTHON" -c "import xarray, netCDF4, yaml, f90nml, scipy, pandas, cdsapi, imdlib" 2>/dev/null && ok "Python: $ME_PYTHON" || bad "Python packages missing in $ME_PYTHON (step 3)"
"$ME_PYTHON" "$ME_REPO/multievent/lib/cases.py" check && ok "study.yaml" || bad "study.yaml checks"
me_log "scheduler: $ME_SCHEDULER"
case $ME_SCHEDULER in
  local) ok "local lanes: $ME_LANES x $ME_NPROCS ranks on $(nproc) cores"; [ $((ME_LANES * ME_NPROCS)) -le "$(nproc)" ] || warn "lanes x ranks > cores" ;;
  pbs)   command -v qsub > /dev/null && ok "qsub: $(command -v qsub)" || bad "ME_SCHEDULER=pbs but no qsub" ;;
  slurm) command -v sbatch > /dev/null && ok "sbatch: $(command -v sbatch)" || bad "ME_SCHEDULER=slurm but no sbatch" ;;
  *) bad "ME_SCHEDULER must be local, pbs or slurm" ;;
esac
me_log "disk"
mkdir -p "$ME_ROOT"
free=$(df -Pk "$ME_ROOT" | awk 'NR==2{print int($4/1048576)}')
[ "$free" -ge 300 ] && ok "$free GB free in $ME_ROOT" || warn "$free GB free in $ME_ROOT; the full study needs about 300 GB (design.md)"
me_log "data servers (downloads can run on another machine; copy $ME_ROOT/data across)"
[ -s "$HOME/.cdsapirc" ] && ok "~/.cdsapirc" || warn "no ~/.cdsapirc: needed for ERA5 (step 8)"
for u in https://psl.noaa.gov/thredds/catalog/Datasets/20thC_ReanV3/catalog.xml https://cds.climate.copernicus.eu/api \
         https://www.imdpune.gov.in/ https://github.com https://pypi.org/simple/xarray/; do
  c=$(curl -s -o /dev/null -m 25 -w "%{http_code}" "$u" || true)
  case $c in 2*|3*|401|403|405) ok "$c $u" ;; *) warn "unreachable ($c) $u" ;; esac
done
[ "$FAIL" = 0 ] && me_log "step 4: all checks passed. Next: bash multievent/05_download_imd.sh" || { me_log "step 4: fix the FAIL lines above"; exit 1; }
