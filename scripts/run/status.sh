#!/usr/bin/env bash
# Progress of every run: model time reached, fraction done, rough time to finish.
#   bash scripts/run/status.sh          (or: watch -n 300 bash scripts/run/status.sh)
source "$(dirname "$0")/env.sh"
$PYTHON - "$RUN_ROOT" "$REPO" <<'EOF'
import re, subprocess, sys, time, yaml
from datetime import datetime
from pathlib import Path
runs, repo = Path(sys.argv[1]), Path(sys.argv[2])
cfg = yaml.safe_load((repo / "config/experiment.yaml").read_text())
now = time.time()
print(f"{'run':38s} {'reached':17s} {'done':>5s}  {'eta':>8s}  note")
for ev, e in cfg["events"].items():
    s0, s1 = (datetime.fromisoformat(e[k]) for k in ("sim_start", "sim_end"))
    span = (s1 - s0).total_seconds()
    for drv in e["drivers"]:
        items = [(f"WRF {ev} {drv}", runs / "wrf" / f"{ev}_{drv}" / "rsl.error.0000", "wrf")]
        items += [(f"RegCM {ev} {drv} {r}", runs / "regcm" / f"{ev}_{drv}_{r}" / "regcm.log", "regcm") for r in ("12km", "03km")]
        for name, log, kind in items:
            if not log.exists():
                print(f"{name:38s} {'-':17s} {'':>5s}  {'':>8s}  not started"); continue
            txt = log.read_bytes()[-200000:].decode(errors="replace")
            if kind == "wrf":
                m = re.findall(r"Timing for main: time (\S+) on domain\s+2", txt) or re.findall(r"Timing for main: time (\S+) on domain\s+1", txt)
                fin = "SUCCESS COMPLETE WRF" in txt
                t = datetime.strptime(m[-1], "%Y-%m-%d_%H:%M:%S") if m else None
            else:
                m = re.findall(r"ATM variables written at\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", txt)
                fin = "successfully reached end" in txt
                t = datetime.strptime(m[-1], "%Y-%m-%d %H:%M:%S") if m else None
            frac = 1.0 if fin else ((t - s0).total_seconds() / span if t else 0.0)
            start = log.parent.stat().st_ctime
            el = now - start
            eta = (el / frac - el) / 3600 if 0 < frac < 1 else 0
            err = "ERROR" if re.search(r"(?i)(fatal|segmentation|NaN found|cfl)", txt[-5000:]) and not fin else ""
            print(f"{name:38s} {str(t)[:16] if t else '-':17s} {100*frac:4.0f}%  {eta:6.1f} h  {'finished' if fin else err}")
EOF
echo; tail -n 2 "$TWCR_HOME"/logs/lane_*.log 2>/dev/null
