#!/usr/bin/env bash
# Step 3 of the multi-event pipeline: the Python environment ($ME_ROOT/venv) and the tests.
#
#   bash multievent/03_install_python.sh
#
# Uses conda if present (environment.yml), otherwise python3 -m venv + pip. Needs Python >= 3.10.
# Without internet access to PyPI/conda-forge: build the environment on a machine that has it
# and copy $ME_ROOT/venv, or set ME_PYTHON in site.env to a Python that has the packages.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
V=$ME_ROOT/venv
PKGS="numpy scipy pandas xarray netCDF4 dask pyyaml f90nml matplotlib tabulate pytest cdsapi>=0.7 imdlib"
if [ ! -x "$V/bin/python" ]; then
  if command -v conda > /dev/null; then
    me_log "conda env $V from environment.yml"
    conda env create -q -p "$V" -f "$ME_REPO/environment.yml" > "$ME_LOGS/03_python.log" 2>&1 || me_die "conda failed: $ME_LOGS/03_python.log"
  else
    python3 -c 'import sys; assert sys.version_info >= (3, 10)' || me_die "python3 < 3.10 and no conda: install Miniforge (github.com/conda-forge/miniforge)"
    me_log "venv $V + pip"
    python3 -m venv "$V"
    "$V/bin/pip" install -q --upgrade pip > "$ME_LOGS/03_python.log" 2>&1
    "$V/bin/pip" install -q $PKGS >> "$ME_LOGS/03_python.log" 2>&1 || me_die "pip install failed: $ME_LOGS/03_python.log"
  fi
fi
P=$V/bin/python
$P -c "import numpy, scipy, pandas, xarray, netCDF4, yaml, f90nml, matplotlib, tabulate, cdsapi, imdlib; print('  xarray', xarray.__version__, 'netCDF4', netCDF4.__version__)" \
  || me_die "packages missing in $V"
(cd "$ME_REPO" && $P -m pytest -q 2>&1 | tail -1)
grep -q "^export ME_PYTHON=$P" "$ME_SITE" 2>/dev/null || echo "  (00_env.sh finds $P by itself; set ME_PYTHON in site.env only to use another one)"
me_log "step 3 done: next bash multievent/04_check_installation.sh"
