"""Patch WRF 4.5 phys/module_mp_thompson.F (mp_physics = 8):
  1. the upstream WRF 4.5.1 Thompson changes (commit 775826b): largest cloud-ice bin 5 -> 2 x D0s
     and rain drops per rain-graupel collision 5 -> 1.5;
  2. bounds fix: without hail-aware graupel the rain-graupel lookup tables (tcg_racg, tmr_racg,
     tcr_gacr, tnr_racg, tnr_gacr) are allocated and filled with a graupel-density dimension of
     extent 1 (dimNRHG = NRHG1 = 1) but were read at idx_bg(k) = idx_bg1 = 5, i.e. outside the
     array. Read them at MIN(idx_bg(k), dimNRHG), which is idx_bg(k) for mp_physics = 38.
   python apply_thompson_fix.py phys/module_mp_thompson.F     (idempotent)"""
import sys
p = sys.argv[1]
s = open(p).read()
if "MIN(idx_bg(k),dimNRHG)" in s:
    print("already patched"); sys.exit(0)
pairs = [("      xDx(nbi+1) = 5.0d0*D0s\n", "      xDx(nbi+1) = 2.0d0*D0s\n"),
         ("            pnr_rcg(k) = -5.*tnr_gacr(", "            pnr_rcg(k) = -1.5*tnr_gacr(")]
for a, b in pairs:
    if s.count(a) != 1:
        sys.exit(f"unexpected source: {a.strip()!r} found {s.count(a)} times (not WRF 4.5?)")
    s = s.replace(a, b)
old = "idx_bg(k),idx_r1,idx_r)"
n = s.count(old)
if n != 8:
    sys.exit(f"expected 8 rain-graupel table lookups, found {n} (not WRF 4.5?)")
s = s.replace(old, "MIN(idx_bg(k),dimNRHG),idx_r1,idx_r)")
open(p, "w").write(s)
print(f"patched: upstream 4.5.1 constants (2) and {n} rain-graupel table lookups")
