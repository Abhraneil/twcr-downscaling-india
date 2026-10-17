#!/usr/bin/env bash
# Progress of every run: model time reached, fraction done, rough time to finish.
# A run whose log has not been written for STALL_MIN minutes (default 30; twice that for RegCM5,
# whose log is buffered) and has not finished is reported as STOPPED: wrf.exe writes
# rsl.error.0000 every time step and RegCM5 regcm.log at least every output time (3 h simulated,
# under 10 min of wall time here), so a silent log means the model is no longer running
# (a crash on another rank leaves no trace in rank 0's log; the lane log has MPI's message).
#   bash scripts/run/status.sh          (or: watch -n 300 bash scripts/run/status.sh)
source "$(dirname "$0")/env.sh"
$PYTHON - "$RUN_ROOT" "$REPO" "${STALL_MIN:-30}" <<'EOF'
import re, subprocess, sys, time, yaml
from datetime import datetime
from pathlib import Path
runs, repo, stall_min = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3])
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
            eta = f"{(el / frac - el) / 3600:6.1f} h" if 0 < frac < 1 else f"{0:6.1f} h"
            silent = (now - log.stat().st_mtime) / 60
            if fin:
                note = "finished"
            elif silent > (stall_min if kind == "wrf" else 2 * stall_min):
                note, eta = f"STOPPED: log silent {silent:.0f} min (see the lane log)", "     -  "
            else:
                note = "ERROR" if re.search(r"(?i)(fatal|segmentation|NaN found|cfl)", txt[-5000:]) else ""
            print(f"{name:38s} {str(t)[:16] if t else '-':17s} {100*frac:4.0f}%  {eta}  {note}")
EOF
echo; tail -n 2 "$TWCR_HOME"/logs/lane_*.log 2>/dev/null
