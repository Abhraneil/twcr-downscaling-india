"""Consistency of the experiment design: domains, scoring boxes, dates, namelists."""
import subprocess
import sys
from datetime import datetime, timedelta

import f90nml
import pytest
import yaml

from conftest import ROOT
from generate_namelists import domain_corners, nest_parent_start

CFG = yaml.safe_load((ROOT / "config/experiment.yaml").read_text())
O, N = CFG["outer_domain"], CFG["inner_domain"]


def test_namelists_are_up_to_date(tmp_path):
    before = {p: p.read_text() for p in (ROOT / "namelists").rglob("*") if p.is_file()}
    subprocess.run([sys.executable, str(ROOT / "scripts/generate_namelists.py")], check=True,
                   capture_output=True)
    after = {p: p.read_text() for p in (ROOT / "namelists").rglob("*") if p.is_file()}
    assert before == after, "namelists/ differ from config/experiment.yaml; run generate_namelists.py"


@pytest.mark.parametrize("ev_name", list(CFG["events"]))
def test_score_box_inside_every_inner_domain_interior(ev_name):
    ev = CFG["events"][ev_name]
    _, _, clat, clon = nest_parent_start(O, N, ev["inner_center"])
    (slat, slon), (nlat, nlon) = domain_corners(N["nx"], N["ny"], N["dx_km"], clat, clon, O["truelat"])
    reg = f90nml.read(ROOT / f"namelists/regcm/{ev_name}_{ev['drivers'][0]}_03km.in")
    buf_deg = reg["boundaryparam"]["nspgx"] * N["dx_km"] / 111.0      # RegCM relaxation zone
    b = ev["score_box"]
    assert b["lat_min"] >= slat + buf_deg and b["lat_max"] <= nlat - buf_deg
    assert b["lon_min"] >= slon + buf_deg and b["lon_max"] <= nlon - buf_deg


@pytest.mark.parametrize("ev_name", list(CFG["events"]))
def test_nest_well_inside_outer_domain(ev_name):
    ips, jps, _, _ = nest_parent_start(O, N, CFG["events"][ev_name]["inner_center"])
    span = (N["nx"] - 1) // N["ratio"]
    reg = f90nml.read(ROOT / f"namelists/regcm/{ev_name}_{CFG['events'][ev_name]['drivers'][0]}_12km.in")
    margin = reg["boundaryparam"]["nspgx"]                        # stay outside the 12 km relaxation zone
    assert ips > margin and jps > margin
    assert ips + span < O["nx"] - margin and jps + span < O["ny"] - margin


@pytest.mark.parametrize("ev_name", list(CFG["events"]))
def test_scoring_windows_inside_simulation_after_spinup(ev_name):
    ev = CFG["events"][ev_name]
    s0, s1 = (datetime.fromisoformat(ev[k]) for k in ("sim_start", "sim_end"))
    w0 = datetime.fromisoformat(ev["score_start"])
    w1 = w0 + timedelta(days=ev["score_ndays"])
    assert w0 >= s0 + timedelta(hours=ev["spinup_hours"])
    assert w1 <= s1
    assert w0.hour == 3                                   # 08:30 IST
    assert s0.month == s1.month                           # RegCM driver files are monthly
    assert (s1 - s0).total_seconds() % 86400 == 0         # RegCM5 aborts unless the run is whole days
    assert s0.hour == 0


def test_wrf_namelist_matches_config():
    for ev_name, ev in CFG["events"].items():
        for drv in ev["drivers"]:
            nml = f90nml.read(ROOT / f"namelists/wrf/namelist.input.{ev_name}_{drv}")
            d = nml["domains"]
            assert d["e_we"] == [O["nx"], N["nx"]] and d["e_sn"] == [O["ny"], N["ny"]]
            assert (N["nx"] - 1) % N["ratio"] == 0 and (N["ny"] - 1) % N["ratio"] == 0
            assert d["dx"] == [int(O["dx_km"] * 1000), int(N["dx_km"] * 1000)]
            assert d["time_step"] <= 6 * O["dx_km"]
            assert nml["physics"]["cu_physics"][1] == 0           # explicit convection at 3 km
            assert nml["time_control"]["interval_seconds"] == 10800
            s = datetime.fromisoformat(ev["sim_start"])
            assert nml["time_control"]["start_year"][0] == s.year


@pytest.mark.parametrize("name", list(CFG.get("post_hoc_runs") or {}))
def test_post_hoc_run_differs_from_baseline_only_in_start(name):
    """A post-hoc WRF run changes one setting of its baseline: the start time."""
    p = CFG["post_hoc_runs"][name]
    ev = CFG["events"][p["event"]]
    nl = lambda f: f90nml.read(ROOT / "namelists/wrf" / f"namelist.input.{f}")
    a, b = nl(p["baseline"]), nl(name)
    timing = {"run_hours", "start_day", "start_hour", "start_month", "start_year"}
    for group in a:
        for key, val in a[group].items():
            if group == "time_control" and key in timing:
                continue
            assert b[group][key] == val, f"{group}.{key} differs from the baseline"
    s0 = datetime.fromisoformat(p["sim_start"])
    s1 = datetime.fromisoformat(ev["sim_end"])
    t = b["time_control"]
    assert (t["start_year"][0], t["start_month"][0], t["start_day"][0], t["start_hour"][0]) == \
        (s0.year, s0.month, s0.day, s0.hour)
    assert t["run_hours"] == (s1 - s0).total_seconds() / 3600
    w0 = datetime.fromisoformat(p["score_start"])
    assert w0 >= s0 + timedelta(hours=ev["spinup_hours"]) and w0.hour == 3
    assert w0 + timedelta(days=p["score_ndays"]) <= s1
    # its restart namelist comes from the same generator
    out = subprocess.run([sys.executable, str(ROOT / "scripts/generate_namelists.py"), "--wrf-restart",
                          name, (s0 + timedelta(hours=12)).strftime("%Y-%m-%d_%H:%M:%S")],
                         check=True, capture_output=True, text=True).stdout
    r = f90nml.reads(out)["time_control"]
    assert r["restart"] is True and r["run_hours"] == t["run_hours"] - 12
