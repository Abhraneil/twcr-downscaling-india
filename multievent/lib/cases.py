#!/usr/bin/env python3
"""Cases of the multi-event study: one per event x driver x physics set.

The single source of case names, dates, domains and namelists (multievent/study.yaml,
docs/multievent/design.md). Called by the numbered scripts; the sub-commands are:

    cases.py events                          table of events with their dates and drivers
    cases.py create [SELECTION] [--force]    case directories + WPS namelists + runs/cases.csv
    cases.py list [SELECTION] [--all]        names of the created cases (--all: of the study), in
                                             submission order
    cases.py wps-list [SELECTION] [--all]    "<event> <driver>" pairs of those cases
    cases.py status [SELECTION] [--all]      state, model time and progress of each case
    cases.py todo [SELECTION] [--fresh]      created cases that can be started now (not finished,
                                             running or queued; --fresh: finished ones too)
    cases.py namelist CASE_DIR [YYYY-MM-DD_HH:MM:SS]
                                             WRF namelist of a case (a restart one with a time)
    cases.py wps-key FILE                    hashes of a WPS namelist: whole file, geogrid part
    cases.py download 20CRv3|ERA5 EVENT      the driver subset for one event
    cases.py check                           consistency checks (also run by the tests)
SELECTION: --events E,.. --drivers D,.. --physics P,.. --cases CASE,..

Run directories ($ME_ROOT/runs):
    wps/<event>/                 geogrid output (geo_em.d01/d02), shared by the drivers
    wps/<event>/<driver>/        intermediate files and met_em files
    cases/<event>_<driver>_<P>/  case.json, namelist.input.template, iofields_d0?.txt, run files
Each case.json holds every resolved setting, so a later edit of study.yaml never changes a
case that already exists: create refuses to overwrite a different one without --force, and with
--force moves the old case directory (and its outputs) to cases/_superseded/. A case is run
under a lock directory, <case>/.run.lock (multievent/lib/run_case.sh).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from generate_namelists import domain_corners, fmt_nml, merc_latlon, merc_xy, nest_parent_start, q  # noqa: E402

sys.path.insert(0, str(REPO / "scripts" / "events"))
from select_events import SEP_DAYS, SEP_KM, km  # noqa: E402  (the selection's declustering rule)

STUDY = REPO / "multievent" / "study.yaml"
UTC03 = timedelta(hours=3)
# 3-D fields written every dynamics_3d_min minutes to wrfdyn_d02_* (P0 only): what the 500 hPa,
# vorticity and column figures need (scripts/scoring/mumbai_figures.py reads the same names)
DYN_3D = ["U", "V", "W", "T", "P", "PB", "PH", "PHB", "QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP",
          "XLAT", "XLONG", "HGT", "PSFC", "MAPFAC_M", "RAINC", "RAINNC"]
# 3-D fields left out of the main history stream (every physics set has a different subset of
# them; names a set does not have are ignored: ignore_iofields_warning)
NOT_IN_HISTORY = ["U", "V", "W", "PH", "PHB", "T", "THM", "P", "PB", "P_HYD", "QVAPOR", "QCLOUD", "QRAIN",
                  "QICE", "QSNOW", "QGRAUP", "QHAIL", "QNICE", "QNRAIN", "QNWFA", "QNIFA", "QNCCN", "QNCLOUD",
                  "REFL_10CM", "CLDFRA", "TKE_PBL", "QKE", "EL_PBL", "SH3D", "SM3D", "RTHCUTEN", "RQVCUTEN",
                  "RQCCUTEN", "RQICUTEN", "RTHRATEN", "RTHBLTEN", "RQVBLTEN", "H_DIABATIC", "QV_DIABATIC",
                  "QC_DIABATIC", "RUBLTEN", "RVBLTEN", "RQCBLTEN", "RQIBLTEN", "W_UP"]


# ------------------------------------------------------------------------------ config ----
def study() -> dict:
    return yaml.safe_load(STUDY.read_text())


def imd_label() -> str:
    return yaml.safe_load((REPO / "config" / "experiment.yaml").read_text())["observations"]["imd_label"]


def runs_root() -> Path:
    return Path(os.environ.get("ME_RUNS", Path(os.environ.get("ME_ROOT", Path.home() / "multievent")) / "runs"))


def _dates(ev: dict) -> dict:
    for k in ("first_label", "last_label"):
        ev[k] = ev[k] if isinstance(ev[k], date) else date.fromisoformat(str(ev[k]))
    return ev


def same_event(a: dict, b: dict) -> bool:
    """Within SEP_DAYS and SEP_KM of each other: one event under the selection's declustering rule."""
    return abs((a["first_label"] - b["first_label"]).days) <= SEP_DAYS and \
        km(a["lat"], a["lon"], b["lat"], b["lon"]) <= SEP_KM


def events(st: dict | None = None) -> dict:
    """The selected events (events_file, if it exists yet) followed by the anchors. An anchor the
    rule has selected anyway is not run twice: the selected event stands for it ("anchor" key)."""
    st = st or study()
    out = {}
    f = REPO / st["events_file"]
    if f.exists():
        out.update({k: _dates(v) for k, v in (yaml.safe_load(f.read_text()) or {}).items()})
    for name, ev in (st.get("anchors") or {}).items():
        ev = _dates(dict(ev))
        twin = [k for k, v in out.items() if same_event(v, ev)]
        if twin:
            out[twin[0]]["anchor"] = name
        else:
            out[name] = ev
    return out


def window_start(label: date, convention: str) -> datetime:
    """Start (03 UTC) of the 24 h an IMD date label covers (observations.imd_label)."""
    d = label - timedelta(days=1) if convention == "backward" else label
    return datetime(d.year, d.month, d.day) + UTC03


def dates(ev: dict, st: dict, convention: str | None = None) -> dict:
    """Scored windows: the event's IMD days plus margin_days on each side; spin-up before them."""
    convention = convention or imd_label()
    m = st["dates"]["margin_days"]
    first = ev["first_label"] - timedelta(days=m)
    last = ev["last_label"] + timedelta(days=m)
    w0 = window_start(first, convention)
    w1 = window_start(last, convention) + timedelta(days=1)
    s0 = w0 - timedelta(hours=st["dates"]["spinup_hours"])
    s1 = datetime(w1.year, w1.month, w1.day) + timedelta(days=1)      # next 00 UTC after the last window
    if s0.hour != 0:
        raise ValueError(f"spin-up must end on a 00 UTC start, got {s0}")
    if s1 > datetime.fromisoformat(st["dates"]["last_sim_end"]):
        raise ValueError(f"simulation would end {s1}, after the last driver time")
    return dict(sim_start=s0.isoformat(), sim_end=s1.isoformat(), score_start=w0.isoformat(),
                score_ndays=(last - first).days + 1, first_label=str(ev["first_label"]),
                last_label=str(ev["last_label"]), imd_label=convention)


def drivers_for(ev: dict, st: dict, convention: str | None = None) -> list[str]:
    s0 = datetime.fromisoformat(dates(ev, st, convention)["sim_start"])
    return [d for d, c in st["drivers"].items() if s0.year >= c["first_year"]]


def outer(st: dict) -> dict:
    g = st["grid"]
    return dict(dx_km=g["d01"]["dx_km"], nx=g["d01"]["nx"], ny=g["d01"]["ny"], center_lat=g["d01"]["center_lat"],
                center_lon=g["d01"]["center_lon"], truelat=g["truelat"])


def nest(ev: dict, st: dict) -> dict:
    """d02 parent start indices centred on the event box, moved inward if too close to the edge."""
    g, o = st["grid"], outer(st)
    inner = dict(nx=g["d02"]["nx"], ny=g["d02"]["ny"], ratio=g["d02"]["ratio"])
    for n in ("nx", "ny"):
        if (inner[n] - 1) % inner["ratio"]:
            raise ValueError(f"d02 {n} - 1 must be a multiple of the nest ratio")
    ips, jps, _, _ = nest_parent_start(o, inner, dict(lat=ev["lat"], lon=ev["lon"]))
    m = g["min_margin_cells"]
    span_i, span_j = (inner["nx"] - 1) // inner["ratio"], (inner["ny"] - 1) // inner["ratio"]
    ips2 = min(max(ips, 1 + m), o["nx"] - m - span_i)
    jps2 = min(max(jps, 1 + m), o["ny"] - m - span_j)
    if not (1 + m <= ips2 and 1 + m <= jps2):
        raise ValueError("d02 does not fit inside d01")
    # actual centre and corners of the nest after the move
    dx = o["dx_km"] * 1000.0
    x0, y0 = merc_xy(o["center_lat"], o["center_lon"], o["truelat"], o["center_lon"])
    ci, cj = ips2 - 0.5 + span_i / 2.0, jps2 - 0.5 + span_j / 2.0
    clat, clon = merc_latlon(x0 + (ci - o["nx"] / 2.0) * dx, y0 + (cj - o["ny"] / 2.0) * dx, o["truelat"], o["center_lon"])
    sw, ne = domain_corners(inner["nx"], inner["ny"], g["d02"]["dx_km"], clat, clon, o["truelat"])
    moved_km = ((ips2 - ips) ** 2 + (jps2 - jps) ** 2) ** 0.5 * o["dx_km"]
    return dict(i_parent_start=ips2, j_parent_start=jps2, center=[round(clat, 3), round(clon, 3)],
                sw=[round(sw[0], 2), round(sw[1], 2)], ne=[round(ne[0], 2), round(ne[1], 2)],
                moved_km=round(moved_km, 1))


def physics(st: dict, pid: str) -> dict:
    p = dict(st["physics_base"])
    p.update(st["physics"][pid])
    return p


def case_dir(name: str, root: Path | None = None) -> Path:
    return (root or runs_root()) / "cases" / name


def created(name: str, root: Path | None = None) -> bool:
    return (case_dir(name, root) / "case.json").exists()


def stored(d: Path) -> dict:
    """The settings a case was created with (case.json without its bookkeeping)."""
    c = json.loads((d / "case.json").read_text())
    return {k: v for k, v in c.items() if k not in ("created", "repo_commit")}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def wps_key(text: str) -> tuple[str, str]:
    """(whole namelist, geogrid group): 10_run_wps.sh marks finished work with these."""
    m = re.search(r"^&geogrid\b.*?^/", text, re.M | re.S)
    return sha(text), sha(m.group(0) if m else "")


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text)
    tmp.replace(path)


def commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "describe", "--always", "--dirty"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:            # noqa: BLE001 - a copy without .git
        return "unknown"


def case_config(name: str, ev: dict, driver: str, pid: str, st: dict) -> dict:
    o = st["output"]
    return dict(case=f"{name}_{driver}_{pid}", event=name, driver=driver, physics_id=pid,
                event_info={k: (str(v) if isinstance(v, date) else v) for k, v in ev.items()},
                dates=dates(ev, st), grid=dict(st["grid"], d02_nest=nest(ev, st)),
                physics=physics(st, pid), prefix=st["drivers"][driver]["prefix"],
                history_min=[o["d01_history_min"], o["d02_history_min"].get(pid, o["d02_history_min"]["other"])],
                dynamics_3d_min=o["dynamics_3d_min"] if pid == "P0" else 0, restart_h=o["restart_h"],
                wps_dir=f"wps/{name}/{driver}", geo_dir=f"wps/{name}", nprocs=st["run"]["nprocs"])


def all_cases(st: dict | None = None, evs=None, drvs=None, phys=None, names=None) -> list[dict]:
    st = st or study()
    order = st["run"]["order"] + [p for p in st["physics"] if p not in st["run"]["order"]]
    out = []
    for pid in order:
        if phys and pid not in phys:
            continue
        for name, ev in events(st).items():
            if evs and name not in evs:
                continue
            for d in drivers_for(ev, st):
                if drvs and d not in drvs:
                    continue
                c = case_config(name, ev, d, pid, st)
                if names and c["case"] not in names:
                    continue
                out.append(c)
    if names:
        unknown = set(names) - {c["case"] for c in out}
        if unknown:
            raise SystemExit(f"not cases of the study (or not in the selection): {', '.join(sorted(unknown))}")
    return out


def selected(a, created_only: bool = True) -> list[dict]:
    """Cases picked by the command-line selection; only those created (09) unless --all."""
    cs = all_cases(None, a.events, a.drivers, a.physics, getattr(a, "cases", None))
    if created_only and not getattr(a, "all", False):
        cs = [c for c in cs if created(c["case"])]
    return cs


# ---------------------------------------------------------------------------- run state ----
# Mirrors me_lock_live in multievent/00_env.sh: a lock directory holds "host pid" in info, which
# its owner touches every 5 min. It is live if that is recent and, on this host, the pid exists.
def lock_live(lock: Path) -> bool:
    info = lock / "info"
    stale_s = 60 * float(os.environ.get("ME_LOCK_STALE_MIN", 30))
    try:
        if not info.exists():          # being created this instant, or left by a crash
            return lock.is_dir() and time.time() - lock.stat().st_mtime < 60
        if time.time() - info.stat().st_mtime > stale_s:
            return False
        host, pid = info.read_text().split()[:2]
    except (OSError, ValueError):
        return False
    if host == socket.gethostname():
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return False
        except (PermissionError, ValueError):
            pass
    return True


SLURM_ACTIVE = {"PENDING", "RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED", "REQUEUED", "REQUEUE_HOLD",
                "REQUEUE_FED", "RESIZING", "SIGNALING", "STAGE_OUT"}


def job_state(job: str) -> str:
    """'active' (queued or running), 'gone', or 'unknown' when the scheduler cannot be asked
    (callers treat unknown as busy, so a case is never submitted twice)."""
    sched = os.environ.get("ME_SCHEDULER", "local")
    try:
        if sched == "pbs":
            r = subprocess.run(["qstat", "-f", job], capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                m = re.search(r"job_state\s*=\s*(\S+)", r.stdout)
                return "gone" if m and m.group(1) in ("F", "X") else "active"
            if re.search(r"unknown job|has finished|been deleted|does not exist", r.stdout + r.stderr, re.I):
                return "gone"
            return "unknown"
        if sched == "slurm":
            r = subprocess.run(["squeue", "-h", "-t", "all", "-j", job, "-o", "%T"], capture_output=True,
                               text=True, timeout=120)
            if r.returncode == 0:
                return "active" if r.stdout.strip() in SLURM_ACTIVE else "gone"
            if "invalid job id" in (r.stdout + r.stderr).lower():
                return "gone"
            return "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return "gone"


def case_state(d: Path) -> tuple[str, str]:
    """(state, note). States: running, queued, queue? (scheduler not answering), done, failed,
    stopped (started, not finished, not running), new."""
    if lock_live(d / ".run.lock"):
        return "running", ""
    jf = d / "job_id"
    if jf.exists():
        job = jf.read_text().strip()
        js = job_state(job)
        if js == "active":
            return "queued", f"job {job}"
        if js == "unknown":
            return "queue?", f"job {job}: the scheduler did not answer"
    if (d / "timing.txt").exists():
        return "done", (d / "timing.txt").read_text().split()[0]
    if (d / "failed.txt").exists():
        return "failed", (d / "failed.txt").read_text().strip().replace("\n", " ")[:70]
    if any((d / f).exists() for f in ("run.log", "real_logs", "rsl.error.0000")):
        return "stopped", "not finished; 11_run_cases.sh continues it"
    return "new", ""


BUSY = ("running", "queued", "queue?")


def reached(d: Path) -> datetime | None:
    rsl = d / "rsl.error.0000"
    if not rsl.exists():
        return None
    with open(rsl, "rb") as fh:
        fh.seek(max(0, rsl.stat().st_size - 100000))
        m = re.findall(r"Timing for main: time (\S+) on domain\s+2", fh.read().decode(errors="replace"))
    return datetime.strptime(m[-1], "%Y-%m-%d_%H:%M:%S") if m else None


# ---------------------------------------------------------------------------- namelists ----
def two(a, b):
    return f"{a}, {b}"


def wps_namelist(c: dict) -> str:
    g, n = c["grid"], c["grid"]["d02_nest"]
    s = datetime.fromisoformat(c["dates"]["sim_start"]).strftime("%Y-%m-%d_%H:%M:%S")
    e = datetime.fromisoformat(c["dates"]["sim_end"]).strftime("%Y-%m-%d_%H:%M:%S")
    groups = [
        ("share", [("wrf_core", q("ARW")), ("max_dom", 2), ("start_date", f"{q(s)}, {q(s)}"),
                   ("end_date", f"{q(e)}, {q(e)}"), ("interval_seconds", 3 * 3600), ("io_form_geogrid", 2),
                   ("opt_output_from_geogrid_path", q("GEO_DIR/"))]),
        ("geogrid", [("parent_id", two(1, 1)), ("parent_grid_ratio", two(1, g["d02"]["ratio"])),
                     ("i_parent_start", two(1, n["i_parent_start"])), ("j_parent_start", two(1, n["j_parent_start"])),
                     ("e_we", two(g["d01"]["nx"], g["d02"]["nx"])), ("e_sn", two(g["d01"]["ny"], g["d02"]["ny"])),
                     ("geog_data_res", f"{q('default')}, {q('default')}"),
                     ("dx", int(g["d01"]["dx_km"] * 1000)), ("dy", int(g["d01"]["dx_km"] * 1000)),
                     ("map_proj", q(g["map_proj"])), ("ref_lat", g["d01"]["center_lat"]),
                     ("ref_lon", g["d01"]["center_lon"]), ("truelat1", g["truelat"]),
                     ("stand_lon", g["d01"]["center_lon"]), ("geog_data_path", q("WPS_GEOG_PATH"))]),
        ("ungrib", [("out_format", q("WPS")), ("prefix", q(c["prefix"]))]),
        ("metgrid", [("fg_name", q(c["prefix"])), ("io_form_metgrid", 2)]),
    ]
    head = (f"! WPS namelist  event={c['event']}  driver={c['driver']}\n"
            "! Written by multievent/lib/cases.py from multievent/study.yaml. Do not edit.\n"
            "! GEO_DIR and WPS_GEOG_PATH are filled in by multievent/10_run_wps.sh; the intermediate files\n"
            "! are written by scripts/preprocess/to_wps.py (no ungrib).\n")
    return head + fmt_nml(groups)


def wrf_namelist(c: dict, restart_from: datetime | None = None) -> str:
    g, n, p = c["grid"], c["grid"]["d02_nest"], c["physics"]
    s0, e = (datetime.fromisoformat(c["dates"][k]) for k in ("sim_start", "sim_end"))
    s = restart_from or s0
    rh = c["restart_h"]
    if (s - s0).total_seconds() % (rh * 3600) or not s0 <= s < e:
        raise ValueError(f"restart time {s} is not on the {rh}-hourly restart grid of {c['case']}")
    run_h = int((e - s).total_seconds() // 3600)
    ratio = g["d02"]["ratio"]
    hist = c["history_min"]
    frames = [rh * 60 // h for h in hist]
    if any(rh * 60 % h for h in hist):
        raise ValueError("history intervals must divide the restart interval")
    pair = lambda a, b=None: two(a, a if b is None else b)
    lst = lambda v: two(*v) if isinstance(v, (list, tuple)) else v
    tc = [("run_days", 0), ("run_hours", run_h), ("run_minutes", 0), ("run_seconds", 0),
          ("start_year", pair(s.year)), ("start_month", pair(f"{s.month:02d}")),
          ("start_day", pair(f"{s.day:02d}")), ("start_hour", pair(f"{s.hour:02d}")),
          ("end_year", pair(e.year)), ("end_month", pair(f"{e.month:02d}")),
          ("end_day", pair(f"{e.day:02d}")), ("end_hour", pair(f"{e.hour:02d}")),
          ("interval_seconds", 3 * 3600), ("input_from_file", ".true., .true."),
          ("history_interval", two(*hist)), ("frames_per_outfile", two(*frames)),
          ("restart", ".true." if restart_from else ".false."), ("restart_interval", rh * 60),
          ("write_hist_at_0h_rst", ".true."),
          ("io_form_history", 2), ("io_form_restart", 2), ("io_form_input", 2), ("io_form_boundary", 2),
          ("iofields_filename", f"{q('iofields_d01.txt')}, {q('iofields_d02.txt')}"),
          ("ignore_iofields_warning", ".true.")]
    if c["dynamics_3d_min"]:
        dm = c["dynamics_3d_min"]
        if rh * 60 % dm:
            raise ValueError("dynamics_3d_min must divide the restart interval")
        tc += [("auxhist2_outname", q("wrfdyn_d<domain>_<date>")), ("auxhist2_interval", two(0, dm)),
               ("frames_per_auxhist2", two(1, rh * 60 // dm)), ("io_form_auxhist2", 2)]
    tc += [("debug_level", 0)]
    groups = [
        ("time_control", tc),
        ("domains", [
            ("time_step", g["time_step_s"]), ("time_step_fract_num", 0), ("time_step_fract_den", 1),
            ("max_dom", 2), ("e_we", two(g["d01"]["nx"], g["d02"]["nx"])), ("e_sn", two(g["d01"]["ny"], g["d02"]["ny"])),
            ("e_vert", pair(g["levels"])), ("p_top_requested", int(g["ptop_hpa"] * 100)),
            ("num_metgrid_levels", "NUM_METGRID_LEVELS"), ("num_metgrid_soil_levels", 4),
            ("dx", two(int(g["d01"]["dx_km"] * 1000), int(g["d02"]["dx_km"] * 1000))),
            ("dy", two(int(g["d01"]["dx_km"] * 1000), int(g["d02"]["dx_km"] * 1000))),
            ("grid_id", two(1, 2)), ("parent_id", two(0, 1)),
            ("i_parent_start", two(1, n["i_parent_start"])), ("j_parent_start", two(1, n["j_parent_start"])),
            ("parent_grid_ratio", two(1, ratio)), ("parent_time_step_ratio", two(1, ratio)),
            ("feedback", p["feedback"]), ("smooth_option", 0)]),
        ("physics", [
            ("mp_physics", lst(p["mp_physics"])), ("ra_lw_physics", lst(p["ra_lw_physics"])),
            ("ra_sw_physics", lst(p["ra_sw_physics"])), ("radt", lst(p["radt"])),
            ("sf_sfclay_physics", lst(p["sf_sfclay_physics"])), ("sf_surface_physics", lst(p["sf_surface_physics"])),
            ("bl_pbl_physics", lst(p["bl_pbl_physics"])), ("bldt", two(0, 0)),
            ("cu_physics", lst(p["cu_physics"])), ("cudt", two(0, 0)),
            ("isfflx", 1), ("ifsnow", 1), ("icloud", 1), ("surface_input_source", 3),
            ("num_soil_layers", 4), ("num_land_cat", 21), ("sf_urban_physics", two(0, 0)),
            ("sst_update", 0), ("aer_opt", 0)]),
        ("fdda", [("grid_fdda", two(0, 0))]),
        ("dynamics", [
            ("hybrid_opt", 2), ("etac", 0.2), ("w_damping", 1), ("diff_opt", two(1, 1)), ("km_opt", two(4, 4)),
            ("diff_6th_opt", two(0, 0)), ("base_temp", 290.0), ("damp_opt", 3), ("zdamp", two(5000.0, 5000.0)),
            ("dampcoef", two(0.2, 0.2)), ("khdif", two(0, 0)), ("kvdif", two(0, 0)),
            ("non_hydrostatic", ".true., .true."), ("moist_adv_opt", two(1, 1)), ("scalar_adv_opt", two(1, 1)),
            ("gwd_opt", two(0, 0))]),
        ("bdy_control", [("spec_bdy_width", 5), ("specified", ".true., .false."), ("nested", ".false., .true.")]),
        ("grib2", []),
        ("namelist_quilt", [("nio_tasks_per_group", 0), ("nio_groups", 1)]),
    ]
    head = (f"! WRF namelist  case={c['case']}  event={c['event']}  driver={c['driver']}  physics={c['physics_id']}\n"
            "! Written by multievent/lib/cases.py from the case's case.json. Do not edit.\n"
            "! NUM_METGRID_LEVELS is filled from the met_em files by multievent/lib/run_case.sh.\n")
    if restart_from:
        head += f"! Continuation from the restart files at {s:%Y-%m-%d_%H:%M:%S}.\n"
    return head + fmt_nml(groups)


def iofields(c: dict, dom: int) -> str:
    """Main history: 2-D fields only. d02 of P0 also gets the 3-D dynamics stream (auxhist2)."""
    lines = [f"-:h:0:{','.join(NOT_IN_HISTORY)}"]
    if dom == 2 and c["dynamics_3d_min"]:
        lines.append(f"+:h:2:{','.join(DYN_3D)}")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- commands ----
def cmd_create(a):
    """Checks everything first and writes only if nothing conflicts."""
    st = study()
    root = runs_root()
    cs = all_cases(st, a.events, a.drivers, a.physics, a.cases)
    problems, plan = [], []
    for c in cs:
        d = case_dir(c["case"], root)
        state, why = "new", ""
        if (d / "case.json").exists():
            tpl = d / "namelist.input.template"
            if stored(d) != c:
                state, why = "changed", "case.json differs from study.yaml"
            elif tpl.exists() and tpl.read_text() != wrf_namelist(c):
                state, why = "changed", "this code writes a different namelist.input.template"
            else:
                state = "unchanged"
        if state == "changed":
            if not a.force:
                problems.append(f"{c['case']}: {why} (the case may have run)")
            elif case_state(d)[0] in BUSY:
                problems.append(f"{c['case']}: running or queued; stop it before recreating it")
        plan.append((c, d, state))
    # WPS: one namelist per event x driver, shared by the physics sets; geogrid per event, shared
    # by the drivers. A change must take every case that uses them along, or the cases left out
    # would be run with met_em files of other settings.
    chosen = {c["case"] for c in cs}
    wps_new = {}
    for c in cs:
        wps_new.setdefault((c["event"], c["driver"]), wps_namelist(c))
    for (e, drv), text in wps_new.items():
        f = root / "wps" / e / drv / "namelist.wps.template"
        if f.exists() and f.read_text() != text:
            if not a.force:
                problems.append(f"wps/{e}/{drv}: WPS settings differ from study.yaml")
            left = [p.name for p in (root / "cases").glob(f"{e}_{drv}_*") if (p / "case.json").exists()
                    and p.name not in chosen]
            if left:
                problems.append(f"wps/{e}/{drv} changes: recreate all its cases together (left out: {', '.join(left)})")
        geo = wps_key(text)[1]
        for g in (root / "wps" / e).glob("*/namelist.wps.template"):
            if g.parent.name not in {d for (e2, d) in wps_new if e2 == e} and wps_key(g.read_text())[1] != geo:
                problems.append(f"{e}: the domains change; recreate it with all its drivers (not {g.parent.name} only)")
    if problems:
        raise SystemExit("\n".join(dict.fromkeys(problems)) + "\nNothing was written. (--force recreates changed "
                         "cases; their old directories go to cases/_superseded/)")
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    counts = {}
    for c, d, state in plan:
        counts[state] = counts.get(state, 0) + 1
        if state == "unchanged" and (d / "namelist.input.template").exists():
            continue
        if state == "changed":
            old = root / "cases" / "_superseded" / f"{c['case']}_{stamp}"
            old.parent.mkdir(parents=True, exist_ok=True)
            d.rename(old)
            print(f"  {c['case']}: settings changed; the old case is now {old}")
        d.mkdir(parents=True, exist_ok=True)
        write_atomic(d / "namelist.input.template", wrf_namelist(c))
        for dom in (1, 2):
            write_atomic(d / f"iofields_d0{dom}.txt", iofields(c, dom))
        if state != "unchanged":       # case.json last: a case directory with it is complete
            write_atomic(d / "case.json", json.dumps(dict(c, created=datetime.now().isoformat(timespec="seconds"),
                                                          repo_commit=commit()), indent=1) + "\n")
    for (e, drv), text in wps_new.items():
        w = root / "wps" / e / drv
        w.mkdir(parents=True, exist_ok=True)
        f = w / "namelist.wps.template"
        if not f.exists() or f.read_text() != text:
            write_atomic(f, text)       # 10_run_wps.sh redoes the pair: its .wps_ok no longer matches
    rows = [dict(case=c["case"], event=c["event"], driver=c["driver"], physics=c["physics_id"],
                 sim_start=c["dates"]["sim_start"], sim_end=c["dates"]["sim_end"],
                 score_start=c["dates"]["score_start"], score_ndays=c["dates"]["score_ndays"],
                 d02_center=" ".join(map(str, c["grid"]["d02_nest"]["center"])),
                 d02_moved_km=c["grid"]["d02_nest"]["moved_km"],
                 anchor=c["event_info"].get("anchor", c["event"] if c["event"] in (st.get("anchors") or {}) else ""))
            for c in all_cases(st)]
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "cases.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(cs)} cases in {root}/cases: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print(f"table of all {len(rows)} cases of the study: {root}/cases.csv")


def cmd_list(a):
    for c in selected(a):
        print(c["case"])


def cmd_wps_list(a):
    seen = []
    for c in selected(a):
        if (c["event"], c["driver"]) not in seen:
            seen.append((c["event"], c["driver"]))
    for e, d in seen:
        print(e, d)


def cmd_todo(a):
    for c in selected(a, created_only=True):
        st = case_state(case_dir(c["case"]))[0]
        if st not in BUSY and (st != "done" or a.fresh):
            print(c["case"])


def cmd_status(a):
    rows, count = [], {}
    for c in selected(a, created_only=False):
        d = case_dir(c["case"])
        if not created(c["case"]):
            st, note, r = "-", "not created (09_create_cases.sh)", None
        else:
            (st, note), r = case_state(d), reached(d)
        count[st] = count.get(st, 0) + 1
        if a.brief:
            print(c["case"], st)
            continue
        if st in ("new", "-") and not a.all:
            continue
        s0, s1 = (datetime.fromisoformat(c["dates"][k]) for k in ("sim_start", "sim_end"))
        frac = 1.0 if st == "done" else ((r - s0).total_seconds() / (s1 - s0).total_seconds() if r else 0.0)
        rows.append(f"{c['case']:34s} {st:8s} {str(r)[:16] if r else '-':16s} {100 * frac:4.0f}%  {note}")
    if a.brief:
        return
    print(f"{'case':34s} {'state':8s} {'model time':16s} {'done':>5s}  note")
    print("\n".join(rows))
    print("\n" + ", ".join(f"{v} {k}" for k, v in sorted(count.items())) + f"  (of {sum(count.values())} cases)")


def cmd_events(a):
    st = study()
    print(f"{'event':16s} {'IMD days':23s} {'simulation (UTC)':33s} {'scored from':17s} days  drivers  d02 centre (moved km)")
    for name, ev in events(st).items():
        dt, n = dates(ev, st), nest(ev, st)
        print(f"{name:16s} {dt['first_label']}..{dt['last_label'][5:]:13s} {dt['sim_start'][:13]} -> {dt['sim_end'][:13]}  "
              f"{dt['score_start'][:13]}  {dt['score_ndays']:4d}  {','.join(drivers_for(ev, st)):8s} "
              f"{n['center'][0]:.2f}N {n['center'][1]:.2f}E ({n['moved_km']:.0f})"
              + (f"  = anchor {ev['anchor']}" if "anchor" in ev else ""))


def cmd_namelist(a):
    """From the stored settings, and only if this code still writes the namelist the case was
    created with: a restart must not pick up a later change of the code."""
    d = Path(a.case_dir)
    c = stored(d)
    tpl = d / "namelist.input.template"
    if tpl.exists() and tpl.read_text() != wrf_namelist(c):
        made = json.loads((d / "case.json").read_text()).get("repo_commit", "?")
        raise SystemExit(f"{d.name}: this code writes a different WRF namelist from the one the case was created with "
                         f"(namelist.input.template, repository {made}). Run it with that version, or recreate it: "
                         f"09_create_cases.sh --cases {d.name} --force")
    t = datetime.strptime(a.time, "%Y-%m-%d_%H:%M:%S") if a.time else None
    sys.stdout.write(wrf_namelist(c, t))


def cmd_wps_key(a):
    print(*wps_key(Path(a.file).read_text()))


def three_hourly(c_dates: dict) -> list[datetime]:
    t, t1 = datetime.fromisoformat(c_dates["sim_start"]), datetime.fromisoformat(c_dates["sim_end"])
    out = []
    while t <= t1:
        out.append(t)
        t += timedelta(hours=3)
    return out


def cmd_download(a):
    st = study()
    ev = events(st)[a.event]
    if a.driver not in drivers_for(ev, st):
        raise SystemExit(f"{a.event} is not run with {a.driver}")
    tt = three_hourly(dates(ev, st))
    sys.path.insert(0, str(REPO / "scripts" / "download"))
    if a.driver == "20CRv3":
        import get_20crv3 as m
    else:
        import get_era5 as m
    m.fetch(a.event, tt, st["driver_box"])


def check(st: dict | None = None) -> list[str]:
    """Design checks: nests inside d01, d01 inside the driver box, spin-up, dates in range."""
    st = st or study()
    prob = []
    o = outer(st)
    sw, ne = domain_corners(o["nx"], o["ny"], o["dx_km"], o["center_lat"], o["center_lon"], o["truelat"])
    b = st["driver_box"]
    if not (b["lat_min"] + 2 <= sw[0] and ne[0] <= b["lat_max"] - 2 and b["lon_min"] + 2 <= sw[1] and ne[1] <= b["lon_max"] - 2):
        prob.append(f"d01 {sw}..{ne} not 2 deg inside the driver box {b}")
    g = st["grid"]
    if g["time_step_s"] % g["d02"]["ratio"]:
        prob.append("time_step must be divisible by the nest ratio")
    for name, ev in events(st).items():
        if "anchor" in ev:
            print(f"note: {name} is the anchor {ev['anchor']} (the rule selected it)", file=sys.stderr)
        try:
            dt = dates(ev, st)
            n = nest(ev, st)
        except ValueError as e:
            prob.append(f"{name}: {e}")
            continue
        s0, w0 = datetime.fromisoformat(dt["sim_start"]), datetime.fromisoformat(dt["score_start"])
        if (w0 - s0) < timedelta(hours=st["dates"]["spinup_hours"]):
            prob.append(f"{name}: spin-up too short")
        if not (n["sw"][0] <= ev["lat"] <= n["ne"][0] and n["sw"][1] <= ev["lon"] <= n["ne"][1]):
            prob.append(f"{name}: event box centre outside its d02 {n['sw']}..{n['ne']}")
        if n["moved_km"] > 0:
            # the box (1.25 deg) must still be at least 2 deg inside the moved nest
            if not (n["sw"][0] + 2 <= ev["lat"] <= n["ne"][0] - 2 and n["sw"][1] + 2 <= ev["lon"] <= n["ne"][1] - 2):
                prob.append(f"{name}: after moving the nest the event is within 2 deg of its edge")
    return prob


def cmd_check(a):
    p = check()
    print("\n".join(p) if p else "study.yaml consistent: nests, driver box, dates")
    sys.exit(1 if p else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sel = argparse.ArgumentParser(add_help=False)
    csl = lambda s: [x for x in s.split(",") if x]
    sel.add_argument("--events", type=csl)
    sel.add_argument("--drivers", type=csl)
    sel.add_argument("--physics", type=csl)
    sel.add_argument("--cases", type=csl)
    sub.add_parser("events").set_defaults(fn=cmd_events)
    p = sub.add_parser("create", parents=[sel])
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_create)
    for name, fn in (("list", cmd_list), ("wps-list", cmd_wps_list), ("status", cmd_status)):
        p = sub.add_parser(name, parents=[sel])
        p.add_argument("--all", action="store_true")
        if name == "status":
            p.add_argument("--brief", action="store_true", help="'<case> <state>' lines only")
        p.set_defaults(fn=fn)
    p = sub.add_parser("todo", parents=[sel])
    p.add_argument("--fresh", action="store_true")
    p.set_defaults(fn=cmd_todo)
    p = sub.add_parser("wps-key")
    p.add_argument("file")
    p.set_defaults(fn=cmd_wps_key)
    p = sub.add_parser("namelist")
    p.add_argument("case_dir")
    p.add_argument("time", nargs="?")
    p.set_defaults(fn=cmd_namelist)
    p = sub.add_parser("download")
    p.add_argument("driver", choices=["20CRv3", "ERA5"])
    p.add_argument("event")
    p.set_defaults(fn=cmd_download)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
