#!/usr/bin/env bash
# Whole experiment in order. Each step is idempotent; re-running skips nothing that
# matters for correctness (outputs are overwritten), so fix and re-run freely.
#   bash scripts/run/run_all.sh
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$REPO"

# 1. data
$PYTHON scripts/download/get_imd.py 1924 2005
$PYTHON scripts/scoring/check_imd_convention.py
$PYTHON scripts/download/get_20crv3.py E1_kerala1924
$PYTHON scripts/download/get_20crv3.py E2_mumbai2005
$PYTHON scripts/download/get_era5.py   E2_mumbai2005

# 2. models
for run in E1_kerala1924:20CRv3 E2_mumbai2005:20CRv3 E2_mumbai2005:ERA5; do
  EV=${run%%:*}; DRV=${run##*:}
  bash scripts/run/run_wps.sh   "$EV" "$DRV"
  bash scripts/run/run_wrf.sh   "$EV" "$DRV"
  bash scripts/run/run_regcm.sh "$EV" "$DRV" both
done

# 3. scoring
for EV in E1_kerala1924 E2_mumbai2005; do
  $PYTHON scripts/postprocess/extract_precip.py "$EV" --runs-root "$RUN_ROOT"
done
$PYTHON scripts/scoring/score_all.py
$PYTHON scripts/scoring/plot_event.py
