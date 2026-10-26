"""The multi-event pipeline (multievent/): case geometry, dates, namelists, and steps 9-14 end to
end with stand-in WRF/WPS executables (tests/integration/fake_wrf)."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import f90nml
import numpy as np
import pytest
import xarray as xr

from conftest import ROOT

sys.path.insert(0, str(ROOT / "multievent" / "lib"))
import cases as C  # noqa: E402

FAKE = ROOT / "tests" / "integration" / "fake_wrf"


def test_study_is_consistent():
    assert C.check() == []


def test_dates_and_drivers_of_the_anchors():
    st = C.study()
    ev = C.events(st)
    d = C.dates(ev["A2_mumbai2005"], st, "backward")
    # IMD days 26-28 July plus one day each side: 24 h windows from 03 UTC 24 July to 03 UTC 29 July
    assert d["score_start"] == "2005-07-24T03:00:00" and d["score_ndays"] == 5
    assert d["sim_start"] == "2005-07-23T00:00:00" and d["sim_end"] == "2005-07-30T00:00:00"
    assert C.drivers_for(ev["A2_mumbai2005"], st) == ["20CRv3", "ERA5"]
    assert C.drivers_for(ev["A1_kerala1924"], st) == ["20CRv3"]
    f = C.dates(ev["A2_mumbai2005"], st, "forward")
    assert f["score_start"] == "2005-07-25T03:00:00"


def test_nest_inside_and_moved_inward_near_the_edge():
    st = C.study()
    n = C.nest({"lat": 19.0, "lon": 73.0}, st)
    assert n["moved_km"] == 0 and n["sw"][0] < 19.0 < n["ne"][0] and n["sw"][1] < 73.0 < n["ne"][1]
    far = C.nest({"lat": 41.0, "lon": 118.0}, st)            # near d01's north-east corner
    g = st["grid"]
    assert far["moved_km"] > 0
    assert far["i_parent_start"] + (g["d02"]["nx"] - 1) // 3 <= g["d01"]["nx"] - g["min_margin_cells"]
    assert far["j_parent_start"] + (g["d02"]["ny"] - 1) // 3 <= g["d01"]["ny"] - g["min_margin_cells"]


def test_namelists_and_restart(tmp_path):
    st = C.study()
    cs = C.all_cases(st, evs=["A2_mumbai2005"], drvs=["ERA5"])
    assert [c["physics_id"] for c in cs] == st["run"]["order"]
    by = {c["physics_id"]: f90nml.reads(C.wrf_namelist(c).replace("NUM_METGRID_LEVELS", "38")) for c in cs}
    p0 = by["P0"]
    # each physics set differs from P0 in its own settings only (and P0 alone writes 3-D output)
    for pid, nml in by.items():
        diff = {(g, k) for g in p0 for k in p0[g] if nml[g].get(k) != p0[g][k]}
        diff = {(g, k) for g, k in diff if not k.startswith(("history_interval", "frames_per_outfile", "auxhist2",
                                                             "frames_per_auxhist2", "io_form_auxhist2"))}
        assert diff == {(g, k) for g in ("physics", "domains") for k in st["physics"][pid] if k in p0[g]}, pid
    assert "auxhist2_interval" in p0["time_control"] and "auxhist2_interval" not in by["P1"]["time_control"]
    assert p0["physics"]["cu_physics"] == [3, 3] and by["P3"]["physics"]["cu_physics"] == [3, 0]
    assert by["P6"]["domains"]["feedback"] == 1
    r = f90nml.reads(C.wrf_namelist(cs[0], datetime(2005, 7, 24, 12)).replace("NUM_METGRID_LEVELS", "38"))
    assert r["time_control"]["restart"] is True and r["time_control"]["run_hours"] == 168 - 36
    with pytest.raises(ValueError):
        C.wrf_namelist(cs[0], datetime(2005, 7, 24, 5))
    w = f90nml.reads(C.wps_namelist(cs[0]))
    assert w["geogrid"]["e_we"] == [241, 151] and w["metgrid"]["fg_name"] == "ERA5"


@pytest.mark.skipif(not os.environ.get("WRF_SRC"), reason="set WRF_SRC to a WRF 4.5 source tree to check keys")
def test_namelist_keys_exist_in_wrf_registry():
    sys.path.insert(0, str(ROOT / "scripts"))
    from check_namelists import wrf_keys
    keys = wrf_keys(Path(os.environ["WRF_SRC"]))
    for c in C.all_cases():
        nml = f90nml.reads(C.wrf_namelist(c).replace("NUM_METGRID_LEVELS", "38"))
        unknown = [(g, k) for g in nml for k in nml[g] if (g, k) not in keys]
        assert not unknown, (c["case"], unknown)


def std_driver(f: Path, times, era5: bool):
    """A small standardised driver file (scripts/common.py format) on the study's driver box."""
    lat, lon = np.arange(-20.0, 50.1, 2.0), np.arange(35.0, 125.1, 2.0)
    plev = np.array([100000, 95000, 92500, 90000, 85000, 80000, 70000, 60000, 50000, 40000, 30000, 25000, 20000,
                     15000, 10000, 5000], "f8")
    nt, nz, ny, nx = len(times), len(plev), len(lat), len(lon)
    full = lambda v, *s: np.full(s, v, "f4")
    tprof = np.clip(300 * (plev / 1e5) ** 0.19, 200, None)
    ds = xr.Dataset(coords={"time": np.array(times, dtype="datetime64[ns]"), "plev": plev, "lat": lat, "lon": lon,
                            "soil_layer": np.arange(4)})
    ds["T"] = (("time", "plev", "lat", "lon"), np.broadcast_to(tprof[None, :, None, None], (nt, nz, ny, nx)).astype("f4"))
    ds["Z"] = (("time", "plev", "lat", "lon"), np.broadcast_to((7400 * np.log(1.013e5 / plev))[None, :, None, None], (nt, nz, ny, nx)).astype("f4"))
    ds["Q"] = (("time", "plev", "lat", "lon"), np.broadcast_to((0.016 * (plev / 1e5) ** 3)[None, :, None, None], (nt, nz, ny, nx)).astype("f4"))
    ds["U"] = (("time", "plev", "lat", "lon"), full(8.0, nt, nz, ny, nx))
    ds["V"] = (("time", "plev", "lat", "lon"), full(1.0, nt, nz, ny, nx))
    for v, x in [("PSFC", 100500.0), ("PMSL", 100800.0), ("T2", 300.0), ("Q2", 0.018), ("U10", 5.0), ("V10", 1.0),
                 ("SKT", 302.0), ("SST", 301.0), ("SEAICE", 0.0), ("SNOW", 0.0)]:
        ds[v] = (("time", "lat", "lon"), full(x, nt, ny, nx))
    ds["ST"] = (("time", "soil_layer", "lat", "lon"), full(299.0, nt, 4, ny, nx))
    ds["SM"] = (("time", "soil_layer", "lat", "lon"), full(0.3, nt, 4, ny, nx))
    ds = ds.assign_coords(soil_top=("soil_layer", [0, 10, 40, 100]), soil_bot=("soil_layer", [10, 40, 100, 200]))
    ds["LANDSEA"] = (("lat", "lon"), ((lat[:, None] > 8) & (lon[None, :] > 72) & (lon[None, :] < 90)).astype("f4") * np.ones((ny, nx), "f4"))
    ds["SOILHGT"] = (("lat", "lon"), full(100.0, ny, nx))
    ds.attrs["source"] = "synthetic"
    f.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(f)
    step = 1 if era5 else 3
    pt = []
    t = times[0]
    while t <= times[-1] + timedelta(days=1):
        pt.append(t)
        t += timedelta(hours=step)
    xr.Dataset({"pr": (("time", "lat", "lon"), full(1.0 / 3600, len(pt), ny, nx))},
               coords={"time": np.array(pt, dtype="datetime64[ns]"), "lat": lat, "lon": lon}).assign_attrs(
        interval_hours=step, units="kg m-2 s-1").to_netcdf(f.with_name(f.stem + "_precip.nc"))


def run(step, env, *args, timeout=900):
    p = subprocess.run(["bash", str(ROOT / "multievent" / step), *args], env=env, capture_output=True, text=True,
                       timeout=timeout)
    assert p.returncode == 0, f"{step} failed:\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}"
    return p.stdout


def wait_for(cases_dir, names, files=("timing.txt", "failed.txt"), secs=600):
    for _ in range(secs):
        if all(any((cases_dir / n / f).exists() for f in files) and not (cases_dir / n / ".run.lock").exists()
               for n in names):
            return
        time.sleep(1)
    raise AssertionError("cases did not finish")


def test_pipeline_steps_9_to_14(tmp_path):
    root = tmp_path / "me"
    site = tmp_path / "site.env"
    site.write_text(f"""export ME_ROOT={root}
export ME_WRF_DIR={FAKE}
export ME_WPS_DIR={FAKE}
export ME_WPS_GEOG={tmp_path}/geog
export ME_SCHEDULER=local ME_LANES=2 ME_NPROCS=2 ME_MPIRUN={FAKE}/mpirun ME_RESUME_WAIT=0
export ME_PYTHON={sys.executable}
""")
    # every 2005 case stops once at 17 UTC 25 July (the fake marks it done in the case directory);
    # with no resumes allowed they fail there
    env = dict(os.environ, ME_SITE=str(site), FAKE_WRF_CRASH_AT="2005-07-25_17:00:00", ME_MAX_RESUMES="0")
    st = C.study()
    for name, ev in C.events(st).items():
        tt = C.three_hourly(C.dates(ev, st))
        for d in C.drivers_for(ev, st):
            std_driver(root / "data" / "drivers" / f"{name}_{d}.nc", tt, d == "ERA5")
    out = run("09_create_cases.sh", env, "--physics", "P0")
    assert "3 cases" in out
    assert "3 unchanged" in run("09_create_cases.sh", env, "--physics", "P0")
    run("10_run_wps.sh", env)
    wps = root / "runs" / "wps"
    for e, d in [("A1_kerala1924", "20CRv3"), ("A2_mumbai2005", "ERA5")]:
        assert len(list((wps / e / d).glob("met_em.d02.*"))) == 57 and (wps / e / d / ".wps_ok").exists()
        assert not list((wps / e / d).glob("TWCR:*")) and not list((wps / e / d).glob("ERA5:*"))
    assert "already there" in run("10_run_wps.sh", env, "--events", "A1_kerala1924")
    run("11_run_cases.sh", env, "--physics", "P0")
    cases_dir = root / "runs" / "cases"
    names = sorted(p.name for p in cases_dir.iterdir())
    wait_for(cases_dir, names)
    status = run("12_status.sh", env)
    assert "1 done" in status and "2 failed" in status, status
    a2 = ["A2_mumbai2005_20CRv3_P0", "A2_mumbai2005_ERA5_P0"]
    assert "gave up after 0 resumes" in (cases_dir / a2[1] / "failed.txt").read_text()

    # a stopped case continues from its restart files without the met_em files
    for d in ("20CRv3", "ERA5"):
        for f in list((wps / "A2_mumbai2005" / d).glob("met_em.d0*")) + [wps / "A2_mumbai2005" / d / ".wps_ok"]:
            f.unlink()
    env["ME_MAX_RESUMES"] = "4"
    out = run("11_run_cases.sh", env)
    assert "2 cases to start" in out
    wait_for(cases_dir, a2, files=("timing.txt",))
    assert "3 done" in run("12_status.sh", env)
    for n in a2:
        assert not (cases_dir / n / "failed.txt").exists()
        assert "continuing" in (cases_dir / n / "run.log").read_text()
        last = f90nml.read(cases_dir / n / "namelist.input")["time_control"]
        assert last["restart"] is True and (last["start_day"][0], last["start_hour"][0]) == (25, 12)
        assert not list((cases_dir / n).glob("wrfrst_*")) and (cases_dir / n / "attempts" / "1").is_dir()
    assert "0 cases to start" in run("11_run_cases.sh", env)

    # one run per case: a held lock refuses a second start; a dead owner's lock is taken over
    c1 = cases_dir / "A1_kerala1924_20CRv3_P0"
    (c1 / "timing.txt").unlink()
    (c1 / ".run.lock").mkdir()
    (c1 / ".run.lock" / "info").write_text(f"{C.socket.gethostname()} {os.getpid()}\n")
    p = subprocess.run(["bash", str(ROOT / "multievent" / "lib" / "run_case.sh"), c1.name], env=env,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 3 and "already running" in p.stdout and not (c1 / "failed.txt").exists()
    assert "running" in run("12_status.sh", env, "--cases", c1.name)
    (c1 / ".run.lock" / "info").write_text(f"{C.socket.gethostname()} 999999999\n")
    p = subprocess.run(["bash", str(ROOT / "multievent" / "lib" / "run_case.sh"), c1.name], env=env,
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0 and (c1 / "timing.txt").exists() and not (c1 / ".run.lock").exists(), p.stderr

    # met_em stay while any case of the study (here P1-P6, not yet created) still needs real.exe
    out = run("14_cleanup.sh", env, "--yes")
    assert "keeping A1_kerala1924 20CRv3: 6 cases of the pair not finished" in out
    assert len(list((wps / "A1_kerala1924" / "20CRv3").glob("met_em.d02.*"))) == 57

    run("13_extract_rain.sh", env)
    daily = xr.open_dataset(root / "data" / "daily" / "A2_mumbai2005_ERA5_P0.nc")["pr"]
    assert daily.sizes["day"] == 5 and str(daily["day"].values[0])[:13] == "2005-07-24T03"
    # fake rain: 3 mm/h at the centre, so about 72 mm/day near (19.0, 73.0)
    assert 40 < float(daily.max()) < 80
    assert (root / "data" / "daily" / "DRIVER_A2_mumbai2005_ERA5.nc").exists()

    # the namelist of a case comes only from the code it was created with
    tpl = c1 / "namelist.input.template"
    tpl.write_text(tpl.read_text() + "! edited\n")
    p = subprocess.run([sys.executable, str(ROOT / "multievent" / "lib" / "cases.py"), "namelist", str(c1)],
                       env=env | {"ME_RUNS": str(root / "runs")}, capture_output=True, text=True)
    assert p.returncode != 0 and "--force" in p.stderr
    p = subprocess.run(["bash", str(ROOT / "multievent" / "09_create_cases.sh"), "--cases", c1.name], env=env,
                       capture_output=True, text=True, timeout=300)
    assert p.returncode != 0 and "different namelist.input.template" in p.stdout + p.stderr

    # a changed case is refused, and with --force recreated after moving the old one aside
    cj = json.loads((c1 / "case.json").read_text())
    (c1 / "case.json").write_text(json.dumps(dict(cj, nprocs=99)))
    p = subprocess.run(["bash", str(ROOT / "multievent" / "09_create_cases.sh"), "--cases", c1.name], env=env,
                       capture_output=True, text=True, timeout=300)
    assert p.returncode != 0 and "Nothing was written" in p.stdout + p.stderr
    assert json.loads((c1 / "case.json").read_text())["nprocs"] == 99
    out = run("09_create_cases.sh", env, "--cases", c1.name, "--force")
    old = list((cases_dir / "_superseded").glob(c1.name + "_*"))
    assert len(old) == 1 and (old[0] / "timing.txt").exists() and (old[0] / "wrfout_d02_1924-07-15_00:00:00").exists() or old
    assert json.loads((c1 / "case.json").read_text())["nprocs"] == 16 and not (c1 / "timing.txt").exists()
    assert "new" in run("12_status.sh", env, "--all", "--cases", c1.name)


def test_scheduler_that_does_not_answer_counts_as_busy(tmp_path):
    runs = tmp_path / "runs"
    c = C.all_cases(evs=["A2_mumbai2005"], drvs=["ERA5"], phys=["P0"])[0]
    d = runs / "cases" / c["case"]
    d.mkdir(parents=True)
    (d / "case.json").write_text(json.dumps(c))
    (d / "job_id").write_text("1234.pbs\n")
    (d / "failed.txt").write_text("walltime\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    todo = lambda: subprocess.run([sys.executable, str(ROOT / "multievent" / "lib" / "cases.py"), "todo"],
                                  env=dict(os.environ, ME_RUNS=str(runs), ME_SCHEDULER="pbs",
                                           PATH=f"{bin_}:/usr/bin:/bin"), capture_output=True, text=True).stdout.split()
    (bin_ / "qstat").write_text("#!/bin/sh\necho 'qstat: cannot connect to server' >&2\nexit 2\n")
    (bin_ / "qstat").chmod(0o755)
    assert todo() == []                       # unknown: never submit twice
    (bin_ / "qstat").write_text("#!/bin/sh\necho 'qstat: Unknown Job Id 1234.pbs' >&2\nexit 153\n")
    assert todo() == [c["case"]]              # the job is gone: failed.txt, so start it again
    (bin_ / "qstat").write_text("#!/bin/sh\necho 'Job Id: 1234.pbs'\necho '    job_state = Q'\n")
    assert todo() == []


def test_an_anchor_the_rule_selects_is_not_run_twice(tmp_path):
    st = C.study()
    f = tmp_path / "events.yaml"
    f.write_text("E07_westcoast2005: {first_label: 2005-07-25, last_label: 2005-07-27, lat: 19.25, lon: 73.25, "
                 "region: West coast and Ghats}\n")
    st["events_file"] = str(f)
    ev = C.events(st)
    assert "A2_mumbai2005" not in ev and ev["E07_westcoast2005"]["anchor"] == "A2_mumbai2005"
    assert "A1_kerala1924" in ev


@pytest.mark.skipif(not os.environ.get("WPS_SRC"), reason="set WPS_SRC to a WPS 4.5 source tree to check keys")
def test_wps_namelist_keys_exist_in_wps_source():
    import re
    decl = {}
    for f in list(Path(os.environ["WPS_SRC"]).rglob("*.F")) + list(Path(os.environ["WPS_SRC"]).rglob("*.f90")):
        t = re.sub(r"&\s*\n\s*&?", " ", f.read_text(errors="replace"))
        for m in re.finditer(r"namelist\s*/\s*(\w+)\s*/([^\n]*)", t, re.I):
            decl.setdefault(m.group(1).lower(), set()).update(n.lower() for n in re.findall(r"[A-Za-z_]\w*", m.group(2).split("!")[0]))
    for c in C.all_cases(phys=["P0"]):
        nml = f90nml.reads(C.wps_namelist(c))
        unknown = [(g, k) for g in nml for k in nml[g] if k not in decl.get(g, set())]
        assert not unknown, (c["case"], unknown)
