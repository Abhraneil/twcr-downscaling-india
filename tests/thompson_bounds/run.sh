#!/usr/bin/env bash
# One column through WRF's own Thompson microphysics (mp_physics = 8) with Fortran bounds
# checking, before and after patches/wrf45_thompson_fix.py (docs/validation.md item 21).
#   bash tests/thompson_bounds/run.sh /path/to/WRF-4.5-source [workdir]
# Expected: the original stops at a rain-graupel table lookup with "Index '5' of dimension 3
# ... above upper bound of 1"; the patched module completes the step. The first run computes
# Thompson's lookup tables (several minutes on one core); the second reuses them.
set -euo pipefail
WRF=$1; HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
WORK=${2:-$(mktemp -d)}
FC=${FC:-gfortran}
for v in original patched; do
  d=$WORK/$v; rm -rf "$d"; mkdir -p "$d"
  cp "$WRF/phys/module_mp_thompson.F" "$WRF/phys/module_mp_radar.F" "$d/"
  [ $v = patched ] && python3 "$REPO/patches/wrf45_thompson_fix.py" "$d/module_mp_thompson.F"
  ( cd "$d"
    $FC -cpp -E -P module_mp_radar.F -o module_mp_radar.f90
    $FC -cpp -E -P module_mp_thompson.F -o module_mp_thompson.f90
    $FC -O2 -g -fcheck=bounds -ffree-line-length-none -fno-range-check -c \
        "$HERE/stubs.f90" module_mp_radar.f90 module_mp_thompson.f90 "$HERE/column.f90"
    $FC ./*.o -o column )
done
( cd "$WORK/original" && ./column > run.log 2>&1 ) || true
cp "$WORK"/original/*.dat "$WORK/patched/" 2>/dev/null || true
( cd "$WORK/patched" && ./column > run.log 2>&1 ) || true
echo "== original";  grep -m2 -E "Fortran runtime error|step done" "$WORK/original/run.log"
echo "== patched";   grep -m2 -E "Fortran runtime error|step done" "$WORK/patched/run.log"
grep -q "Index '5' of dimension 3 of array 't[a-z]*_\(racg\|gacr\)' above upper bound of 1" "$WORK/original/run.log" \
  && grep -q "step done" "$WORK/patched/run.log" && ! grep -q "Fortran runtime error" "$WORK/patched/run.log" \
  && echo "PASS: out-of-bounds read in the original, none after the patch" || { echo "FAIL (logs in $WORK)"; exit 1; }
